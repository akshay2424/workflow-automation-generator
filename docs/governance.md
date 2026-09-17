# Governance & Security

Conceptual for this exercise, but each mechanism below is actually implemented
in the code, not just described.

## PII handling

- **Where:** `src/pii_redact.py`, applied in `src/cli.py` before any text is
  passed to the extraction stage.
- **What's redacted:** emails, phone numbers, SSN-like patterns, employee IDs,
  credit-card-like number sequences — each replaced with a typed placeholder
  (e.g. `[EMAIL_REDACTED]`) so the LLM retains enough structure to reason
  about the process ("send confirmation to [EMAIL_REDACTED]") without ever
  seeing the actual value.
- **Why redact before sending, not after:** the goal is data minimization —
  don't rely on the LLM provider's data handling policy to protect sensitive
  data; minimize what leaves the environment in the first place.
- **Honest limitation:** the current redaction is regex-based, which is
  explainable but not exhaustive (it won't catch a name like "John Smith"
  written in prose). A production deployment would use a proper PII/NER
  model (e.g. Microsoft Presidio, AWS Comprehend PII) as a drop-in
  replacement for this module — the pipeline's interface (`redact(text) ->
  RedactionResult`) doesn't need to change to make that swap.

## Secrets management

- The Groq API key is read from an environment variable
  (`GROQ_API_KEY`, see `src/config.py`), never hardcoded.
- `.env.example` is committed; `.env` itself is git-ignored (`.gitignore`) so
  a real key can never accidentally land in version control.
- In a real enterprise deployment this would move to a secrets manager
  (AWS Secrets Manager, HashiCorp Vault, or similar) with rotation policy —
  noted here as the natural next step past environment variables.

## Audit trail

- **Where:** `src/audit.py`, called on every extraction call and every
  workflow generation outcome (success or failure).
- **What's logged:** timestamp, document id, model used, cache hit/miss,
  token counts, estimated cost, latency, and validation outcome — written as
  append-only JSON lines to `audit_log.jsonl`.
- **Why this matters for governance, not just cost:** the log answers "which
  model processed this document, when, and did its output pass validation
  cleanly or need escalation?" — the kind of question a compliance review
  would ask about any automated decision-adjacent system.
- **Production note:** JSONL-on-disk is the right choice for a take-home
  exercise (no infrastructure needed, trivially inspectable). A real
  deployment would ship this to an append-only, access-controlled store
  (e.g. S3 + Athena, or a SIEM) so the log itself can't be tampered with by
  whoever operates the pipeline.

## Access control (conceptual)

Not implemented in this exercise (no multi-user auth layer), but the design
intentionally leaves room for it:
- The pipeline is a set of pure functions/stages, not a stateful service —
  adding an auth layer means wrapping `src/cli.py`'s entrypoint (or a future
  API layer) with standard authentication/authorization, without touching
  the extraction/validation logic.
- Document access itself (which documents a given user/system can submit)
  would be enforced at the ingestion boundary (`src/ingest.py`), the single
  place all documents enter the pipeline — the natural choke point for that
  control.

## Data retention

- Cached LLM responses (`.cache/`) and generated workflows (`output/`) are
  git-ignored — they're treated as regenerable artifacts, not something to
  persist indefinitely or commit alongside source code.
- A production system would define an explicit retention policy for the
  audit log and cache (e.g. cache TTL, audit log retained per compliance
  requirement) — flagged here as a policy decision, not a technical one,
  which is why it isn't hardcoded into the pipeline.
