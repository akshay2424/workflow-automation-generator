# AI Stack — Tools Chosen and Why

## LLM: Groq (openai/gpt-oss-20b for extraction, openai/gpt-oss-120b for escalation)

**Why Groq instead of OpenAI/Anthropic directly:**
Groq offers a genuinely free tier — no credit card required to get an API
key — while still giving access to strong open-weight models on custom
inference hardware (LPUs) that's noticeably faster than typical GPU-hosted
inference. For a take-home exercise a reviewer needs to actually run,
removing the "you need a paid API key to see this work" barrier is a real
practical advantage.

**A note on model choice, stated honestly:** an earlier version of this
project defaulted to `llama-3.1-8b-instant` / `llama-3.3-70b-versatile`.
Groq has since moved both of those to Enterprise-only access
("Contact Sales" pricing, no self-serve free-tier access) — a 404
`model_not_found` error is what that looks like in practice. Groq's model
lineup changes over time (see `https://console.groq.com/docs/models` for
the current list), so this project's defaults are checked against that page
and updated when needed; `src/config.py` documents this explicitly at the
point where the model names are set, so it's a one-line fix rather than a
mystery next time it happens.

**Why `openai/gpt-oss-20b` as the default, not the larger model:**
Extraction here is a narrow, structured task — "read this SOP, output a
list of steps with actor/condition/next-step" — not open-ended reasoning.
A 20B open-weight model handles structured extraction well, responds
faster, and uses less of the free tier's rate-limit budget per call than
the 120B model.

**Why `openai/gpt-oss-120b` as an escalation path, not the default:**
Some documents may have genuinely ambiguous or tangled process descriptions
where the smaller model can't produce a structurally valid workflow even
after one retry. Rather than looping forever or giving up, we escalate that
one document to the larger, more capable model. This is the same
"small/fast model for triage, larger model for the hard cases" pattern
you'd use with paid providers (e.g. gpt-4o-mini vs gpt-4o) — the engineering
discipline is identical, and the pattern transfers directly if this were
ever moved to a different provider.

**Rate limits are the practical constraint on Groq's free tier:**
Groq's free tier needs no credit card to start, gated by requests/tokens
per minute rather than a hard dollar cap up front. This is why caching (see
`src/cache.py`) and the capped retry-then-escalate logic (max 2 extra calls
per document) matter here — they manage rate-limit budget the same way
they'd manage dollar budget on a metered provider.

**Why not a locally hosted model (e.g. via Ollama)?**
Considered it. Groq gives comparable "no local GPU needed" convenience with
less setup burden for a reviewer running this for the first time, and
faster inference than most local setups. Self-hosting remains the right
call at high enough volume that free-tier rate limits become a bottleneck.

## Strict JSON schema mode, not best-effort JSON object mode

Both `openai/gpt-oss-20b` and `openai/gpt-oss-120b` support Groq's
**strict** structured-outputs mode (`response_format={"type": "json_schema",
"json_schema": {"strict": True, "schema": {...}}}`) — the same category of
guarantee as OpenAI's structured outputs. The model is constrained at the
token level to only ever produce output matching the exact schema in
`src/extractor.py::STEP_SCHEMA`: every field present, correct types, no
extras, every time. This is a genuine upgrade over best-effort
`{"type": "json_object"}` mode (which only guarantees valid JSON *syntax*,
not a specific shape) — it means no manual shape-checking code is needed on
top of the API call, and a whole category of "syntactically valid but
missing a field" failure simply can't happen. Semantic correctness (right
actors, right branching logic) is still checked separately by
`workflow_builder.validate()` — schema compliance and semantic correctness
are different guarantees, and strict mode only gives you the first one.

## A real gotcha: reasoning models can return an empty response

`openai/gpt-oss-20b`/`120b` are **reasoning models** — before writing the
final JSON answer, they spend some tokens on internal chain-of-thought.
Early testing against the real API surfaced a confusing failure: a 400
error (`json_validate_failed`) with an *empty* `failed_generation` field,
on some documents but not others. Root cause, confirmed against Groq's own
community reports of the same issue: at the default reasoning effort, a
longer or more complex document can cause the model to spend its entire
token budget on reasoning, leaving nothing left to actually write the JSON
answer — a technically-valid request that comes back with nothing to
parse. Two settings fix this, both set explicitly in
`src/extractor.py::extract_steps()`: `reasoning_effort="low"` (this is a
narrow extraction task, not one that benefits from deep chain-of-thought),
and an explicit, generous `max_completion_tokens` rather than relying on
whatever default the API applies. A defensive check was also added so that
if this ever happens again, the error message explains what happened
instead of a cryptic parsing exception.

## No vector database / RAG framework

Track 2 is about **sequence extraction from a document set**, not retrieval
across a large corpus. Each document is processed independently to produce
its own workflow. Introducing a vector store here would be complexity without
a matching problem — the rubric explicitly rewards judgment, not defaulting
to whatever's trendiest, and RAG isn't the right tool for this shape of task.

## No agent framework (LangGraph / CrewAI)

The pipeline is a fixed sequence of deterministic stages with one LLM call
and one conditional retry/escalation loop — not a multi-agent conversation
with open-ended tool use. A hand-rolled sequential pipeline (`src/cli.py`) is
easier to test, debug, and explain than wrapping it in an agent framework
whose abstractions (graphs, agents, memory) aren't doing real work here.
Framework overhead should be justified by genuine orchestration complexity;
this pipeline doesn't have it.

## Mermaid for diagrams, not Graphviz/matplotlib

Mermaid renders natively in GitHub and most Markdown viewers. A reviewer can
open `docs/architecture.md` or any generated `.diagram.mmd` file and see the
diagram with zero extra tooling — no need to install Graphviz or run a script
to view an image.

## No mock/offline mode — fail fast with clear setup instructions instead

This project always calls the real Groq API; there's no hand-written
stand-in data keyed by filename. That's a deliberate choice: a per-filename
lookup table only works for the exact documents it was written for, and
would silently break (or need special-casing) the moment someone drops in
an unrecognized file — which defeats the point of a genuinely generic
extraction pipeline.

Instead, the friction of needing an API key is handled directly:
`src/config.py::require_api_key()` checks for a key before any processing
starts, and if it's missing, prints the exact steps to get a free one
(no credit card needed) and exits cleanly — rather than the program
crashing later with a confusing authentication error from deep inside the
API client. See the README's setup section for those same steps.
