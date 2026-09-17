# Evaluation Results

## How to generate these numbers

```bash
cp .env.example .env     # then paste your free Groq key in
pip install -r requirements.txt
python -m eval.run_eval
```

This requires a real Groq API key (see README) — there is no mock/offline
mode in this project, so these numbers reflect the actual model's behavior,
not a hand-written stand-in. Run it, then paste the output below this line
as your submitted evaluation results.

## What the harness measures, and how to read it

`eval/run_eval.py` runs the real pipeline against the 3 sample documents,
compares the extracted steps against `eval/ground_truth.py` (a hand-labeled
answer key), and reports:

| Metric | What it answers | A low score means |
|---|---|---|
| Step recall | Of the steps that should be there, how many did we find? | The model is **missing** real steps |
| Step precision | Of the steps we found, how many were actually correct? | The model is **hallucinating** steps |
| Actor accuracy | For matched steps, did we get the right role/actor? | The model got the *who*, not just the *what* |
| Transition recall | Of the correct connections between steps, how many did we find? | Branching/sequencing logic wasn't captured |
| Validation pass rate | Did the output pass structural checks without retry? | The model's raw output isn't shaped correctly |

The onboarding document's ground truth deliberately includes one step
(`notify_hold_status`) that a real model may or may not surface as its own
distinct step — see the note in `eval/ground_truth.py` for why. A perfect
100% across every document on a first run would actually be a small red
flag (it would suggest the check isn't genuinely independent) — a document
or two landing in the 80–95% range is a normal, credible result and still
worth reporting honestly rather than only showing the docs that scored
well.

## Latency and rate-limit usage

Every real call logs `prompt_tokens`, `completion_tokens`, and `latency_ms`
to `audit_log.jsonl` (see `src/audit.py`). After running `eval.run_eval`,
you can inspect that file directly to see real numbers per document — this
is also the data `docs/cost_optimization.md`'s rate-limit budgeting
discussion is based on.

```bash
cat audit_log.jsonl
```

## Also run the deterministic tests

The validation logic itself (not dependent on any LLM call) has its own
test suite that requires no API key at all:

```bash
python -m pytest tests/ -v
```

These pass or fail on pure logic — useful to run first to confirm the
non-LLM half of the pipeline is solid before spending any API calls on the
LLM half.
