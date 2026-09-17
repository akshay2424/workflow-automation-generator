"""
Simple disk-based cache for LLM calls.

Why a hand-rolled cache instead of a library?
- The interviewer wants to see you understand WHY caching saves cost, not just
  that you called a library. The key insight to be able to explain:
  cache_key = sha256(redacted_text + model_name + prompt_version)
  This means: same document + same model + same prompt version => cache hit,
  $0 marginal cost. Changing the prompt (bumping PROMPT_VERSION) safely
  invalidates stale cache entries instead of silently serving outdated results.
"""
import hashlib
import json
import os
from typing import Optional

from src.config import CACHE_DIR


def _key(text: str, model: str, prompt_version: str) -> str:
    raw = f"{model}:{prompt_version}:{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def get(text: str, model: str, prompt_version: str) -> Optional[dict]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, _key(text, model, prompt_version) + ".json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def set(text: str, model: str, prompt_version: str, value: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, _key(text, model, prompt_version) + ".json")
    with open(path, "w") as f:
        json.dump(value, f, indent=2)
