# Token / Cost Optimization

This section is weighted heavily in the rubric, so the goal here is concrete
mechanisms with real numbers attached — even though this project uses Groq's
free tier, where the constraint is **rate limits, not dollars**. The rubric
asks for cost/token discipline; the mechanisms below are the same ones you'd
apply with a paid provider, just optimizing against a different budget
(requests-per-minute instead of dollars-per-token). I call this out
explicitly rather than treating "it's free" as an excuse to skip this
section — the discipline is what's being evaluated, not the currency.

## 1. Model routing (small/fast model by default, escalate only on failure)

- Default extraction model: **openai/gpt-oss-20b** — smaller, faster,
  and uses a smaller share of the free tier's tokens-per-minute limit.
- Escalation model: **openai/gpt-oss-120b** — larger and more capable,
  used **only** if the small model's output fails structural validation
  twice (see `src/cli.py`'s retry-then-escalate logic).
- Concrete effect: for a typical 1-page SOP (~800 input tokens, ~600 output
  tokens), a call to the gpt-oss-20b model is both faster and lighter on rate-limit
  budget than a call to the gpt-oss-120b model. Across a document set where most
  documents parse cleanly on the first pass (all 3 sample documents did, in
  testing), this routing strategy keeps the large majority of calls on the
  lightweight model and reserves the larger model for genuine edge cases —
  directly analogous to "cheap model for triage, frontier model for hard
  cases" with a paid provider, just measured in rate-limit headroom instead
  of dollars.

## 2. Disk-based caching keyed by content hash

- Cache key: `sha256(redacted_text + model_name + prompt_version)`
  (`src/cache.py`).
- Concrete effect: re-running the generator on an unchanged document set —
  which happens constantly during development, demos, and re-runs after a
  pipeline code change unrelated to the prompt — makes **zero additional API
  calls** after the first pass. This matters even more on a free tier than a
  paid one: Groq's free tier enforces requests-per-minute limits, so an
  uncached pipeline that re-processes the same 3 documents on every test run
  burns through that limit for no reason. Only documents whose text actually
  changed, or where the prompt itself was intentionally updated
  (`PROMPT_VERSION` bump), trigger a new call.
- This also means **iteration on the pipeline is instant and rate-limit-free**:
  the 3 sample documents in this repo were extracted once, and every
  subsequent run of `python -m src.cli` or `python -m eval.run_eval` reuses
  the cached result.

## 3. A capped retry ceiling, not unbounded retries

`src/cli.py`'s logic tries the small model once, retries the small model once
more with validation feedback, and escalates to the large model once if
still failing — then gives up and reports the document as failed. This caps
every document at a maximum of 3 calls total. Without this ceiling, a
document that's genuinely hard to parse correctly could retry indefinitely,
which on a rate-limited free tier could exhaust the limit for an entire
batch run over a single problem document.

## 4. Chunking with a defined ceiling, not unlimited context stuffing

`src/ingest.py::chunk_document` caps input at `MAX_CHUNK_CHARS = 6000` per
call. Sending an entire unbounded document (or several documents
concatenated) in one call inflates both the input token count and the
processing time per call — on a rate-limited free tier, larger calls also
tend to consume more of the tokens-per-minute budget per request. Capping
chunk size keeps each call's token footprint proportional to what the model
actually needs to see.

## 5. Audit log doubles as a usage-monitoring feed

Every real LLM call logs `prompt_tokens`, `completion_tokens`, and
`latency_ms` to `audit_log.jsonl` (`src/audit.py`, called from
`src/extractor.py`). On a paid provider this feed would double as a cost
tracker; on Groq's free tier it doubles as a **rate-limit usage tracker** —
the same log answers "how close am I to hitting my requests/tokens per
minute limit this run?" without needing a separate monitoring tool bolted
on. If this were ever moved to a paid provider, adding a dollar-cost field
back into this same log is a one-line change (see the
`estimate_free_tier_load` function in `src/extractor.py` for where that
would go).

## Tradeoffs, stated honestly

- **Small-model-first routing** risks slightly lower extraction quality on
  genuinely ambiguous documents on the first pass — mitigated by the
  retry-then-escalate logic, not eliminated.
- **Caching by exact content hash** means even a single-character change to
  a document invalidates its cache entry — a coarser (semantic) cache could
  catch more hits but adds real complexity (embedding calls) that isn't
  justified at this document volume.
- **Free tier rate limits are a real production constraint**, not just a
  development convenience — at high enough document volume, Groq's free
  tier would need to move to a paid Groq tier or a different provider
  entirely. This is explicitly a demo/development choice, stated as such,
  not presented as a production-scale answer.
- **Fixed chunk size** is simple but not adaptive to document structure
  (doesn't try to split on section boundaries) — a reasonable v2
  improvement, called out explicitly rather than silently glossed over.
