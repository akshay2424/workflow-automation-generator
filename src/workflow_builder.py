"""
Workflow builder: raw extracted steps -> validated state-machine graph.

This is deliberately a SEPARATE stage from extraction (src/extractor.py).
Why separate them instead of asking the LLM to "just output a valid state
machine"?
  - We can validate deterministically with plain Python, which is free and
    instant, instead of paying for another LLM call to check its own work.
  - Validation failures give us structured error messages we can feed back
    into a retry prompt (see extractor.extract_steps's validation_errors arg).
  - It makes the pipeline's correctness testable in isolation (see tests/).

The output shape is intentionally close to a BPMN-like graph (nodes + typed
transitions) so a reviewer can see how this would map onto a real automation
engine (Camunda, Temporal, AWS Step Functions, etc.) rather than being a
bespoke format nobody could act on.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional


class WorkflowValidationError(Exception):
    """Raised when a generated workflow fails structural validation."""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class WorkflowGraph:
    doc_id: str
    steps: List[dict]  # raw step dicts, id/description/actor/condition/next_step_ids/is_start/is_end

    def to_state_machine(self) -> dict:
        """Export as a BPMN-like JSON structure an automation engine could consume."""
        return {
            "doc_id": self.doc_id,
            "states": {
                s["id"]: {
                    "description": s["description"],
                    "actor": s["actor"],
                    "condition": s["condition"],
                    "type": "start" if s["is_start"] else ("end" if s["is_end"] else "task"),
                }
                for s in self.steps
            },
            "transitions": [
                {"from": s["id"], "to": target, "guard": s["condition"]}
                for s in self.steps
                for target in s["next_step_ids"]
            ],
            "start_state": next((s["id"] for s in self.steps if s["is_start"]), None),
            "end_states": [s["id"] for s in self.steps if s["is_end"]],
        }


def validate(steps: List[dict]) -> List[str]:
    """Return a list of human-readable validation errors (empty list = valid).

    Checks performed (each maps to a real correctness property of a runnable
    workflow, not an arbitrary rule):
    1. Exactly one start state.
    2. At least one end state.
    3. Every next_step_id referenced actually exists as a step.
    4. Every non-end step has at least one outgoing transition.
    5. Every state is reachable from the start state (no orphan islands).
    6. No duplicate step ids.
    """
    errors = []
    ids = [s["id"] for s in steps]
    id_set = set(ids)

    if len(ids) != len(id_set):
        dupes = {i for i in ids if ids.count(i) > 1}
        errors.append(f"Duplicate step ids found: {dupes}")

    starts = [s for s in steps if s["is_start"]]
    if len(starts) != 1:
        errors.append(f"Expected exactly 1 start state, found {len(starts)}")

    ends = [s for s in steps if s["is_end"]]
    if len(ends) == 0:
        errors.append("No end state found — workflow has no terminal step")

    for s in steps:
        for target in s["next_step_ids"]:
            if target not in id_set:
                errors.append(f"Step '{s['id']}' references unknown next_step_id '{target}'")

        if not s["is_end"] and len(s["next_step_ids"]) == 0:
            errors.append(f"Non-terminal step '{s['id']}' has no outgoing transitions")

    if starts and not errors:
        reachable = _reachable_from(starts[0]["id"], steps)
        unreachable = id_set - reachable
        if unreachable:
            errors.append(f"Unreachable states from start: {unreachable}")

    return errors


def _reachable_from(start_id: str, steps: List[dict]) -> set:
    by_id = {s["id"]: s for s in steps}
    seen = set()
    stack = [start_id]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in by_id:
            continue
        seen.add(cur)
        stack.extend(by_id[cur]["next_step_ids"])
    return seen


def build(doc_id: str, steps: List[dict]) -> WorkflowGraph:
    """Validate and wrap steps into a WorkflowGraph, or raise WorkflowValidationError."""
    errors = validate(steps)
    if errors:
        raise WorkflowValidationError(errors)
    return WorkflowGraph(doc_id=doc_id, steps=steps)
