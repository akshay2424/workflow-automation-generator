"""
Unit tests for the deterministic parts of the pipeline (validation, graph
building). These need NO API key and NO network access — they test the logic
that doesn't depend on the LLM, which is exactly the part we can test cheaply
and exhaustively. LLM-dependent behavior is covered separately in eval/.
"""
import pytest
from src.workflow_builder import validate, build, WorkflowValidationError


def _step(id, next_ids=None, is_start=False, is_end=False, condition=None):
    return {
        "id": id,
        "description": f"desc for {id}",
        "actor": "tester",
        "condition": condition,
        "next_step_ids": next_ids or [],
        "is_start": is_start,
        "is_end": is_end,
    }


def test_valid_linear_workflow():
    steps = [
        _step("a", ["b"], is_start=True),
        _step("b", ["c"]),
        _step("c", [], is_end=True),
    ]
    assert validate(steps) == []


def test_valid_branching_workflow():
    steps = [
        _step("start", ["approve", "reject"], is_start=True),
        _step("approve", ["done"], condition="amount < 500"),
        _step("reject", ["done"], condition="amount >= 500"),
        _step("done", [], is_end=True),
    ]
    assert validate(steps) == []


def test_missing_start_state_fails():
    steps = [_step("a", ["b"]), _step("b", [], is_end=True)]
    errors = validate(steps)
    assert any("start state" in e for e in errors)


def test_multiple_start_states_fails():
    steps = [
        _step("a", ["c"], is_start=True),
        _step("b", ["c"], is_start=True),
        _step("c", [], is_end=True),
    ]
    errors = validate(steps)
    assert any("start state" in e for e in errors)


def test_no_end_state_fails():
    steps = [_step("a", ["b"], is_start=True), _step("b", ["a"])]
    errors = validate(steps)
    assert any("end state" in e for e in errors)


def test_dangling_reference_fails():
    steps = [
        _step("a", ["nonexistent"], is_start=True),
    ]
    errors = validate(steps)
    assert any("unknown next_step_id" in e for e in errors)


def test_unreachable_state_fails():
    steps = [
        _step("a", ["b"], is_start=True),
        _step("b", [], is_end=True),
        _step("orphan", [], is_end=True),  # not connected to start
    ]
    errors = validate(steps)
    assert any("Unreachable" in e for e in errors)


def test_duplicate_ids_fails():
    steps = [
        _step("a", ["b"], is_start=True),
        _step("a", [], is_end=True),  # duplicate id
    ]
    errors = validate(steps)
    assert any("Duplicate" in e for e in errors)


def test_build_raises_on_invalid():
    steps = [_step("a", ["missing"], is_start=True)]
    with pytest.raises(WorkflowValidationError):
        build("test_doc", steps)


def test_build_succeeds_and_exports_state_machine():
    steps = [
        _step("a", ["b"], is_start=True),
        _step("b", [], is_end=True),
    ]
    graph = build("test_doc", steps)
    sm = graph.to_state_machine()
    assert sm["start_state"] == "a"
    assert sm["end_states"] == ["b"]
    assert sm["states"]["a"]["type"] == "start"
    assert sm["states"]["b"]["type"] == "end"
    assert {"from": "a", "to": "b", "guard": None} in sm["transitions"]
