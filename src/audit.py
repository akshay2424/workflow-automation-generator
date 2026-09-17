"""
Append-only audit log — governance requirement.

Every LLM call (and, going forward, every workflow generation event) writes one
JSON line here: what document, what model, whether it was a cache hit, tokens,
cost, latency, and a timestamp. This is deliberately boring and simple —
JSONL is trivially greppable/parseable and needs no infrastructure, which is
the right choice for "even if only conceptually for this exercise" per the PDF.

In a real enterprise deployment this would ship to a proper audit store
(e.g. append-only S3 + Athena, or a SIEM) with access controls on who can
read it — noted in docs/governance.md.
"""
import json
import time
from src.config import AUDIT_LOG_PATH


def log_event(event_type: str, **fields) -> None:
    record = {"timestamp": time.time(), "event": event_type, **fields}
    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
