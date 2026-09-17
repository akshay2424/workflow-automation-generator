"""
Extraction stage: unstructured document text -> structured list of workflow steps.

This is the "show how you extract intent and sequence from unstructured input"
requirement from the PDF. Key design choices to be ready to explain:

1. We use Groq's STRICT JSON schema mode (response_format={"type": "json_schema",
   "json_schema": {"strict": True, ...}}). Groq's openai/gpt-oss-20b and
   openai/gpt-oss-120b models support this the same way OpenAI's structured
   outputs do: the model is constrained at the token level to only ever
   produce output matching the exact schema, so the shape is guaranteed --
   we don't need to write our own manual shape-checking code on top of it
   (earlier drafts of this project did, back when only best-effort
   "json_object" mode was available; strict mode makes that unnecessary).

2. Every extraction call goes through the cache first (src/cache.py) -- this
   matters even on a free tier, because Groq's free tier has rate limits
   (requests per minute), and caching avoids burning through that limit on
   repeated runs.

3. Every call (cache hit or miss) is written to the audit log with token
   counts and latency -- this is the audit trail required by the governance
   section, and it's the data source for the cost/rate-limit writeup.

4. If the model returns steps that fail our own SEMANTIC validation
   (workflow_builder.validate -- e.g. no single start state, orphan steps),
   we retry ONCE on the same model with the validation errors appended to
   the prompt. If it fails again, we escalate to a larger model
   (openai/gpt-oss-120b) rather than looping indefinitely. Note this is a
   different kind of failure than a SHAPE failure: strict mode guarantees
   the JSON shape is right, but says nothing about whether the *content* is
   semantically correct (right actors, right branching) -- that's what
   workflow_builder.validate() and the retry/escalation loop are for.

This module always calls the real Groq API -- there is no mock/offline mode.
Any .txt/.md document you drop into data/sample_docs/ goes through the exact
same generic flow: no per-document hardcoding, no lookup table keyed by
filename.
"""
import json
import time
from dataclasses import dataclass
from typing import List, Optional

from src.config import GROQ_API_KEY, PROMPT_VERSION
from src import cache
from src.audit import log_event

_client = None  # created only on first real API call (lazy singleton)


def _get_client():
    # Imported here, not at the top of the file, so that a clear
    # config.require_api_key() error can fire before we ever need this
    # import to succeed (see src/cli.py's main()).
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


SYSTEM_PROMPT = """You are a process analyst. You read operational documents \
(SOPs, support tickets, policy docs) and extract the SEQUENCE OF STEPS they \
describe as a structured workflow.

Rules:
- Each step is a discrete state or action in the process.
- Identify the actor responsible for each step (role or system name).
- Identify conditions/branches explicitly (e.g. "if amount > $500, requires \
manager approval") as separate steps with a `condition` field and multiple \
possible `next_step_ids`.
- The first step must have no incoming transitions; mark it with is_start=true.
- Any step with no outgoing transitions is a terminal step; mark it with \
is_end=true.
- Do not invent steps that are not supported by the document text.
- Use short, unique snake_case ids for each step (e.g. "submit_request").
- If the document does not describe any kind of process or sequence of
  steps at all, return an empty steps list rather than inventing one.
"""

# Strict JSON schema: openai/gpt-oss-20b and openai/gpt-oss-120b use
# constrained decoding against this schema, so the model's output is
# GUARANTEED to match this shape exactly -- every field present, correct
# types, no extras. Strict mode requires every property to be listed in
# "required" and every object to set "additionalProperties": false; a
# genuinely optional field (like "condition") is expressed as a nullable
# type (["string", "null"]) rather than being left out of "required".
STEP_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "workflow_steps",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "actor": {"type": "string"},
                            "condition": {"type": ["string", "null"]},
                            "next_step_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "is_start": {"type": "boolean"},
                            "is_end": {"type": "boolean"},
                        },
                        "required": [
                            "id", "description", "actor", "condition",
                            "next_step_ids", "is_start", "is_end",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["steps"],
            "additionalProperties": False,
        },
    },
}


@dataclass
class ExtractionResult:
    steps: List[dict]
    model_used: str
    cache_hit: bool
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int


def extract_steps(doc_id: str, redacted_text: str, model: str,
                   use_cache: bool = True,
                   validation_errors: Optional[str] = None) -> ExtractionResult:
    """Turn document text into a list of step dicts, via a real Groq API call.

    Works identically for ANY document -- there's no per-filename lookup or
    special-casing. A brand new file you drop into data/sample_docs/ goes
    through exactly this same path.
    """
    cache_key_text = redacted_text if not validation_errors else (
        redacted_text + "\n\n[RETRY_CONTEXT]\n" + validation_errors
    )

    if use_cache and not validation_errors:
        cached = cache.get(cache_key_text, model, PROMPT_VERSION)
        if cached:
            log_event("extract_steps", doc_id=doc_id, model=model,
                      cache_hit=True, cost_usd=0.0)
            return ExtractionResult(
                steps=cached["steps"], model_used=model, cache_hit=True,
                latency_ms=0.0, prompt_tokens=0, completion_tokens=0,
            )

    user_prompt = f"Document:\n{redacted_text}"
    if validation_errors:
        user_prompt += (
            f"\n\nYour previous attempt failed validation with these errors:\n"
            f"{validation_errors}\nPlease fix and return a valid workflow."
        )

    client = _get_client()
    start = time.time()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format=STEP_SCHEMA,
        temperature=0,
        # openai/gpt-oss-* are REASONING models: before writing the actual
        # JSON answer, they spend tokens on internal chain-of-thought. At
        # Groq's default reasoning effort, that reasoning can consume the
        # entire token budget on a longer document, leaving nothing left to
        # write the actual answer -- which surfaces as a confusing 400
        # "json_validate_failed" with an EMPTY failed_generation, not as a
        # normal validation error. Two settings fix this:
        #   - reasoning_effort="low": spend fewer tokens reasoning, since
        #     this is a narrow extraction task, not a task that benefits
        #     from deep chain-of-thought.
        #   - max_completion_tokens: an explicit, generous ceiling so
        #     reasoning + the JSON answer both have room, rather than
        #     relying on whatever default the API applies.
        reasoning_effort="low",
        max_completion_tokens=8192,
    )
    latency_ms = (time.time() - start) * 1000

    content = response.choices[0].message.content
    if not content:
        # Should be rare now that reasoning_effort/max_completion_tokens are
        # set (see the call above), but if it ever happens again, fail with
        # a message that actually explains what went wrong, rather than a
        # confusing json.JSONDecodeError or TypeError from json.loads(None).
        raise ValueError(
            f"Groq returned an empty response for '{doc_id}' (model={model}). "
            f"This usually means the reasoning model used its whole token "
            f"budget on internal reasoning and had nothing left for the "
            f"actual answer -- try raising max_completion_tokens in "
            f"src/extractor.py if this persists."
        )

    # With strict: true, this is guaranteed to be valid JSON matching
    # STEP_SCHEMA exactly -- no manual shape-checking needed here.
    parsed = json.loads(content)

    usage = response.usage

    log_event("extract_steps", doc_id=doc_id, model=model, cache_hit=False,
              prompt_tokens=usage.prompt_tokens,
              completion_tokens=usage.completion_tokens,
              latency_ms=latency_ms, cost_usd=0.0)

    if use_cache and not validation_errors:
        cache.set(cache_key_text, model, PROMPT_VERSION, parsed)

    return ExtractionResult(
        steps=parsed["steps"], model_used=model, cache_hit=False,
        latency_ms=latency_ms, prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )


# Groq's free tier needs no credit card to start, with generous rate limits
# (requests/tokens per minute) rather than a hard dollar cap. We still log
# token counts (above) so usage against those limits is observable. Standard
# pay-as-you-go pricing (should you exceed free-tier limits, or move to a
# paid plan) is published at https://console.groq.com/docs/models and can
# change -- check there for current numbers rather than trusting a
# hardcoded table here.
def estimate_free_tier_load(prompt_tokens: int, completion_tokens: int) -> int:
    """Return total tokens used, for tracking against Groq's rate limits."""
    return prompt_tokens + completion_tokens
