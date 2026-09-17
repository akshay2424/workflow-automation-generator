# Workflow Automation Generator (Track 2)

Turns unstructured documents (SOPs, tickets, policy docs) into an
**executable workflow** — a validated state machine, not a summary.

Built for the CIS AI Engineering Interview Challenge — Track 2.

This is a **generic pipeline**: any `.txt`/`.md` document you drop into
`data/sample_docs/` is processed the same way as the three bundled samples.
There's no hardcoded lookup table keyed by filename — every document goes
through the exact same extraction, validation, and export logic.

## Setup — getting a free Groq API key

This project needs a Groq API key to run (extraction is a real LLM call —
there's no offline/demo mode). Groq's free tier needs **no credit card**.

1. Go to **https://console.groq.com/keys**
2. Sign up or log in.
3. Click **"Create API Key"**, name it anything, and copy the key
   (starts with `gsk_...`).
4. In this project folder, copy the example env file:
   ```bash
   cp .env.example .env
   ```
5. Open `.env` in a text editor and paste your key in:
   ```
   GROQ_API_KEY=gsk_your_actual_key_here
   ```
6. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

That's it. If you forget this step, running the pipeline prints these exact
instructions again and exits cleanly instead of crashing with a confusing
error (see `src/config.py::require_api_key()`).

## Quick start

```bash
python -m src.cli
```

You should see output like:

```
--- Processing sop_refund_process.txt ---
  Redacted PII: {'EMAIL': 1}
  Extracted 9 steps using openai/gpt-oss-20b (cache_hit=False)
  [OK] Wrote output/sop_refund_process.workflow.json and .../diagram.mmd
```

Generated files land in `output/`. Open any `.diagram.mmd` file in a
Markdown viewer (or paste into https://mermaid.live) to see the visual
diagram.

## Try it on your own document

Drop any `.txt` or `.md` file into `data/sample_docs/` and run
`python -m src.cli` again — it's processed identically to the bundled
samples, no code changes needed. If a document doesn't actually describe a
process, the model is instructed to return an empty step list rather than
inventing one, and that document is reported as failed in the summary
rather than crashing the run.

## Run the generated workflow (prove it's executable)

```bash
python -m src.executor output/sop_refund_process.workflow.json
```

This walks through the workflow state by state, and asks you to choose a
branch at decision points (like "was the amount under $500?"). Add `--auto`
to run it non-interactively (auto-picks the first branch at each decision).

## Run the tests

```bash
python -m pytest tests/ -v
```

These test the validation logic directly — no API key, no network needed.

## Run the evaluation

```bash
python -m eval.run_eval
```

Compares extracted workflows against hand-labeled ground truth and prints
precision/recall/accuracy numbers. Requires a Groq API key (see
`eval/eval_results.md` for what these numbers mean and how to regenerate
them).

## Project structure

```
src/
  config.py           - all tunable settings + require_api_key() setup check
  ingest.py           - loads and chunks documents (any .txt/.md file)
  pii_redact.py        - strips PII before any LLM call
  extractor.py           - the real Groq LLM call + retry/escalation logic
  workflow_builder.py     - validates steps, builds the state machine
  executor.py               - runs a workflow.json end-to-end
  diagram.py                 - exports a Mermaid diagram
  cli.py                      - orchestrates the full pipeline
  audit.py                     - append-only audit log

data/sample_docs/      - 3 realistic sample documents (SOP, ticket, policy)
                          -- drop your own .txt/.md files in here too
eval/
  ground_truth.py      - hand-labeled correct answers (for the 3 samples)
  run_eval.py           - computes precision/recall/accuracy
  eval_results.md         - what these numbers mean + how to regenerate
tests/
  test_workflow_builder.py  - unit tests for validation logic (no API key needed)
docs/
  architecture.md       - pipeline diagram and design rationale
  ai_stack.md             - tool choices and why
  cost_optimization.md      - concrete rate-limit/efficiency mechanisms
  governance.md               - PII/secrets/audit/access-control notes
```

## Known limitations (stated honestly, not hidden)

- **Multi-chunk documents** are concatenated back into one string before
  extraction rather than merged step-by-step per chunk. Fine for the sample
  documents (all single-chunk); a longer real-world SOP set would need a
  proper cross-chunk merge step.
- **PII redaction is regex-based**, not a full NER model — see
  `docs/governance.md` for the production alternative.
- **Chunking is fixed-size**, not boundary-aware (doesn't try to split on
  section headers) — see `docs/cost_optimization.md`.
- **A genuinely unrelated document** (not a process description at all) is
  handled gracefully — the model is instructed to return an empty step
  list, and/or validation fails cleanly and the document is reported as
  failed — but isn't silently "fixed" or force-fit into a fake workflow.

## Deliverables checklist (per the PDF)

1. ✅ Working code + this README
2. ✅ Architecture diagram — `docs/architecture.md`
3. ✅ AI Stack writeup — `docs/ai_stack.md`
4. ✅ Evaluation results — `eval/eval_results.md`
5. ✅ Cost optimization writeup — `docs/cost_optimization.md`
6. ✅ Governance & security note — `docs/governance.md`
