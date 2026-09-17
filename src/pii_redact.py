"""
PII redaction layer — governance requirement.

Design decision: redaction happens BEFORE text is sent to the LLM API, not after.
This matters for the governance writeup: we are not relying on the LLM provider's
data handling policy to protect sensitive data — we minimize what leaves our
environment in the first place ("data minimization" principle).

This is intentionally regex-based and conservative for this exercise. In a real
enterprise deployment you'd swap this for a proper PII/NER model (e.g. Presidio,
AWS Comprehend PII) — noted explicitly in docs/governance.md so it's clear this
is a stand-in, not a claim that regex is sufficient for production.
"""
import re
from dataclasses import dataclass, field

# Patterns are intentionally simple/explainable — each one maps to a category
# a reviewer can immediately recognize.
_PATTERNS = {
    "EMAIL": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "PHONE": re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"),
    "SSN_LIKE": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "EMPLOYEE_ID": re.compile(r"\bEMP-\d{4,8}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
}


@dataclass
class RedactionResult:
    redacted_text: str
    counts: dict = field(default_factory=dict)  # category -> number of redactions


def redact(text: str) -> RedactionResult:
    """Replace PII patterns with typed placeholders (e.g. [EMAIL_REDACTED]).

    Placeholders are typed (not just "[REDACTED]") so the LLM can still reason
    about structure ("send confirmation to [EMAIL_REDACTED]") without seeing
    the actual value.
    """
    counts = {}
    out = text
    for label, pattern in _PATTERNS.items():
        matches = pattern.findall(out)
        if matches:
            counts[label] = len(matches)
            out = pattern.sub(f"[{label}_REDACTED]", out)
    return RedactionResult(redacted_text=out, counts=counts)
