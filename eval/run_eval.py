"""
run_eval.py
------------
This script answers the question: "how good is the extraction, really?"
with actual numbers, not just "it ran and looked fine."

For each sample document, we:
  1. Run it through the real pipeline (extract steps + build workflow).
  2. Compare the extracted steps against our hand-written ground_truth.py.
  3. Compute simple, well-known metrics:
       - Step recall:    of the steps that SHOULD be there, how many did we find?
       - Step precision: of the steps we found, how many were actually correct?
       - Actor accuracy: for steps we matched, did we get the right actor/role?
       - Transition recall: of the correct connections between steps, how many
         did we find? (this measures whether the branching logic was captured)
       - Validation pass rate: did the output pass our structural checks
         (single start, no orphans, etc.) without needing a retry?
  4. Also record latency and cost per document (from the audit log), so we
     have real timing/cost numbers, not guesses.

Run it with:  python -m eval.run_eval
"""
import statistics
import sys

from src.config import RunConfig, DATA_DIR, require_api_key
from src.ingest import load_documents, chunk_document
from src.pii_redact import redact
from src.extractor import extract_steps
from src.workflow_builder import validate
from eval.ground_truth import GROUND_TRUTH


def score_one_document(doc_id: str, extracted_steps: list) -> dict:
    """Compare extracted_steps against the ground truth for this document."""
    truth = GROUND_TRUTH[doc_id]

    extracted_ids = {s["id"] for s in extracted_steps}
    expected_ids = truth["expected_step_ids"]

    matched_ids = extracted_ids & expected_ids
    missed_ids = expected_ids - extracted_ids
    extra_ids = extracted_ids - expected_ids

    step_recall = len(matched_ids) / len(expected_ids) if expected_ids else 0.0
    step_precision = len(matched_ids) / len(extracted_ids) if extracted_ids else 0.0

    # Actor accuracy: only check steps where we have a known-correct actor
    # AND the model actually extracted that step.
    actor_checks = 0
    actor_correct = 0
    extracted_by_id = {s["id"]: s for s in extracted_steps}
    for step_id, correct_actor in truth["expected_actors"].items():
        if step_id in extracted_by_id:
            actor_checks += 1
            if extracted_by_id[step_id]["actor"].strip().lower() == correct_actor.lower():
                actor_correct += 1
    actor_accuracy = (actor_correct / actor_checks) if actor_checks else None

    # Transition recall: of the (from, to) pairs that should exist, how many
    # did we actually produce?
    extracted_transitions = set()
    for s in extracted_steps:
        for target in s["next_step_ids"]:
            extracted_transitions.add((s["id"], target))
    expected_transitions = truth["expected_transitions"]
    matched_transitions = extracted_transitions & expected_transitions
    transition_recall = (
        len(matched_transitions) / len(expected_transitions) if expected_transitions else 0.0
    )

    validation_errors = validate(extracted_steps)

    return {
        "doc_id": doc_id,
        "step_recall": step_recall,
        "step_precision": step_precision,
        "missed_ids": missed_ids,
        "extra_ids": extra_ids,
        "actor_accuracy": actor_accuracy,
        "transition_recall": transition_recall,
        "validation_passed": len(validation_errors) == 0,
        "validation_errors": validation_errors,
    }


def run():
    require_api_key()
    cfg = RunConfig()
    docs = load_documents(DATA_DIR)

    all_scores = []
    print("=" * 60)
    print("RUNNING EVALUATION")
    print("=" * 60)

    for doc in docs:
        if doc.doc_id not in GROUND_TRUTH:
            continue  # skip docs we haven't hand-labeled

        chunks = chunk_document(doc, max_chars=cfg.max_chunk_chars)
        full_text = "\n".join(c.text for c in chunks)
        redaction = redact(full_text)

        result = extract_steps(doc.doc_id, redaction.redacted_text,
                                cfg.extraction_model, use_cache=cfg.use_cache)

        scores = score_one_document(doc.doc_id, result.steps)
        scores["latency_ms"] = result.latency_ms
        scores["model_used"] = result.model_used
        all_scores.append(scores)

        print(f"\n--- {doc.doc_id} ---")
        print(f"  Step recall:        {scores['step_recall']:.0%}")
        print(f"  Step precision:     {scores['step_precision']:.0%}")
        if scores["missed_ids"]:
            print(f"  Missed steps:       {scores['missed_ids']}")
        if scores["actor_accuracy"] is not None:
            print(f"  Actor accuracy:     {scores['actor_accuracy']:.0%}")
        print(f"  Transition recall:  {scores['transition_recall']:.0%}")
        print(f"  Validation passed:  {scores['validation_passed']}")
        print(f"  Latency:            {scores['latency_ms']:.1f} ms")

    print("\n" + "=" * 60)
    print("OVERALL AVERAGES")
    print("=" * 60)
    avg_recall = statistics.mean(s["step_recall"] for s in all_scores)
    avg_precision = statistics.mean(s["step_precision"] for s in all_scores)
    avg_transition_recall = statistics.mean(s["transition_recall"] for s in all_scores)
    validation_pass_rate = sum(s["validation_passed"] for s in all_scores) / len(all_scores)

    print(f"  Avg step recall:        {avg_recall:.0%}")
    print(f"  Avg step precision:     {avg_precision:.0%}")
    print(f"  Avg transition recall:  {avg_transition_recall:.0%}")
    print(f"  Validation pass rate:   {validation_pass_rate:.0%}")
    print(f"  Documents evaluated:    {len(all_scores)}")

    return all_scores


if __name__ == "__main__":
    run()
