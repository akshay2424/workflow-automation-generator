"""
Central configuration for the Workflow Automation Generator.

Why a single config module instead of scattering constants?
- Interviewers/reviewers can see every cost-relevant knob (model choice, cache TTL,
  chunk size) in one place, which directly supports the "cost optimization writeup"
  requirement — you can point at this file and say "here's where I made the tradeoffs."
- Swapping models (e.g. 8B -> 70B for a harder doc set) is a one-line change.
"""
import os
import sys
from dataclasses import dataclass

# Load a .env file automatically if one exists, so the person running this
# only has to fill in .env once rather than manually exporting environment
# variables every time. This is optional -- if python-dotenv isn't installed,
# we just skip it silently and fall back to real environment variables
# (e.g. ones set in CI, or exported in the shell).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- LLM settings -----------------------------------------------------------
# We use Groq. Rationale (belongs in AI stack writeup):
#   - Groq has a genuinely free tier (no credit card required to start),
#     which matters a lot for a take-home exercise a reviewer needs to run.
#   - Groq runs open-source/open-weight models on custom inference hardware
#     ("LPUs") that make inference extremely fast.
#   - We keep a "small/fast model first, escalate on failure" pattern:
#     openai/gpt-oss-20b is smaller and faster; openai/gpt-oss-120b is a
#     larger, more capable model used only if the small one's output fails
#     validation twice. Both support Groq's STRICT JSON schema mode (see
#     src/extractor.py), which guarantees the model's output always matches
#     our required shape -- no manual shape-checking needed.
#
#   Note on model choice: Groq's available model lineup changes over time
#   (models get added, moved to Enterprise-only, or deprecated -- see
#   https://console.groq.com/docs/models for the current list). If a model
#   name below ever returns a 404 "model_not_found" error, check that page
#   for the current production model IDs and update these two lines.
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "openai/gpt-oss-20b")
ESCALATION_MODEL = os.environ.get("ESCALATION_MODEL", "openai/gpt-oss-120b")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# --- Chunking -----------------------------------------------------------
# Long SOPs get split into chunks before extraction so we (a) stay well under
# context limits and (b) can cache+reuse chunks independently if only part of
# a document changes between runs.
MAX_CHUNK_CHARS = 6000
CHUNK_OVERLAP_CHARS = 300

# --- Caching -----------------------------------------------------------
# Disk-based cache keyed by sha256(document text + model + prompt version).
# This is the single biggest efficiency lever: re-running the generator on
# the same doc set (e.g. during development/demo) makes zero extra API calls
# after the first pass -- important on Groq's rate-limited free tier.
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")
PROMPT_VERSION = "v1"  # bump this to invalidate cache when prompts change

# --- Paths -----------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sample_docs")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")
AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "audit_log.jsonl")


@dataclass
class RunConfig:
    """Bundle of settings passed through the pipeline for a single run."""
    extraction_model: str = EXTRACTION_MODEL
    escalation_model: str = ESCALATION_MODEL
    max_chunk_chars: int = MAX_CHUNK_CHARS
    use_cache: bool = True


def require_api_key() -> None:
    """Check that a Groq API key is available; if not, print clear setup
    instructions and exit, instead of letting the program crash later with
    a confusing authentication error from deep inside the Groq client.

    Called once, at the very start of the CLI entrypoint (src/cli.py), so
    the very first thing someone sees if they haven't set up a key yet is
    "here's exactly how to fix this" rather than a stack trace.
    """
    if GROQ_API_KEY.strip():
        return

    print("""
No Groq API key found. This project needs one to run (it's free).

Here's how to get one, step by step:

  1. Go to https://console.groq.com/keys
  2. Sign up or log in (no credit card required for the free tier).
  3. Click "Create API Key", give it any name, and copy the key that
     starts with "gsk_...".
  4. In this project folder, copy the example env file:
         cp .env.example .env
  5. Open .env in a text editor and paste your key in:
         GROQ_API_KEY=gsk_your_actual_key_here
  6. Install the Groq client if you haven't already:
         pip install groq python-dotenv
  7. Run this command again:
         python -m src.cli

That's it -- no billing information needed for the free tier.
""")
    sys.exit(1)
