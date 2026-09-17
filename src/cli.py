"""
Main entrypoint: runs the full pipeline end-to-end for every document in
data/sample_docs, producing output/<doc_id>.workflow.json and
output/<doc_id>.diagram.mmd for each.

Pipeline: ingest -> redact -> extract (cached) -> validate/build -> export
On validation failure: retry once with error feedback, then escalate model.

This is a fully generic flow: any .txt/.md file placed in data/sample_docs/
is processed the same way as the three bundled samples. There's no
per-filename special-casing anywhere in this pipeline.
"""
import json
import os
import sys

from src.config import RunConfig, DATA_DIR, OUTPUT_DIR, require_api_key
from src.ingest import load_documents, chunk_document
from src.pii_redact import redact
from src.extractor import extract_steps
from src.workflow_builder import build, WorkflowValidationError, validate
from src.diagram import to_mermaid
from src.audit import log_event


def process_document(doc, cfg: RunConfig):
    print(f"\n--- Processing {doc.doc_id} ---")

    chunks = chunk_document(doc, max_chars=cfg.max_chunk_chars)
    # For this exercise most docs are single-chunk; if a doc produced multiple
    # chunks we'd merge per-chunk step lists here. Kept simple deliberately —
    # noted as a known limitation in the README.
    full_text = "\n".join(c.text for c in chunks)

    redaction = redact(full_text)
    if redaction.counts:
        print(f"  Redacted PII: {redaction.counts}")

    model = cfg.extraction_model
    result = extract_steps(doc.doc_id, redaction.redacted_text, model,
                            use_cache=cfg.use_cache)
    print(f"  Extracted {len(result.steps)} steps using {model} "
          f"(cache_hit={result.cache_hit})")

    errors = validate(result.steps)
    if errors:
        print(f"  Validation failed ({len(errors)} errors). Retrying with feedback...")
        result = extract_steps(doc.doc_id, redaction.redacted_text, model,
                                use_cache=False,
                                validation_errors="; ".join(errors))
        errors = validate(result.steps)

    if errors:
        print(f"  Still failing after retry. Escalating to {cfg.escalation_model}...")
        result = extract_steps(doc.doc_id, redaction.redacted_text,
                                cfg.escalation_model, use_cache=False,
                                validation_errors="; ".join(errors))
        errors = validate(result.steps)

    if errors:
        print(f"  [FAILED] Could not produce a valid workflow: {errors}")
        log_event("workflow_generation_failed", doc_id=doc.doc_id, errors=errors)
        return None

    graph = build(doc.doc_id, result.steps)
    state_machine = graph.to_state_machine()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    base = doc.doc_id.rsplit(".", 1)[0]
    wf_path = os.path.join(OUTPUT_DIR, f"{base}.workflow.json")
    diagram_path = os.path.join(OUTPUT_DIR, f"{base}.diagram.mmd")

    with open(wf_path, "w") as f:
        json.dump(state_machine, f, indent=2)
    with open(diagram_path, "w") as f:
        f.write(to_mermaid(wf_path))

    print(f"  [OK] Wrote {wf_path} and {diagram_path}")
    log_event("workflow_generation_succeeded", doc_id=doc.doc_id,
              num_states=len(state_machine["states"]))
    return wf_path


def main():
    # Fail fast with clear instructions if there's no API key, instead of
    # letting the program crash later, deep inside the Groq client, with a
    # confusing authentication error.
    require_api_key()

    cfg = RunConfig()
    docs = load_documents(DATA_DIR)
    if not docs:
        print(f"No documents found in {DATA_DIR}")
        sys.exit(1)

    results = []
    for doc in docs:
        # Wrapped per-document: a single malformed/unusual document (bad
        # JSON from the model, a network hiccup, an empty file, whatever)
        # is reported as a failure for THAT document only. It never takes
        # down the rest of the batch -- important once you start feeding
        # this arbitrary, unvetted files instead of the curated samples.
        try:
            path = process_document(doc, cfg)
        except Exception as e:
            print(f"  [FAILED] Unexpected error processing {doc.doc_id}: {e}")
            log_event("workflow_generation_failed", doc_id=doc.doc_id,
                       errors=[str(e)])
            path = None
        results.append((doc.doc_id, path))

    print("\n=== Summary ===")
    for doc_id, path in results:
        status = "OK" if path else "FAILED"
        print(f"  [{status}] {doc_id}")


if __name__ == "__main__":
    main()
