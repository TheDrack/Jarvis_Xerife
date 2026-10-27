"""Tests for repairing small-model plan output without widening validation."""
import pytest

from app.multiagent.execution_plan import DeclarativePlanInterpreter, PlanValidationError
from app.multiagent.model_plan_adapter import parse_model_plan


def _ids():
    counter = iter(range(1, 100))
    return lambda: f"exec-{next(counter)}"


def test_fenced_plan_with_prose_and_missing_fields_runs_end_to_end():
    text = (
        "Sure! Here is the plan:\n```json\n"
        '{"steps": ['
        '{"step_id": "find", "tool": "lookup", "args": {}, "output_fields": ["id"]},'
        '{"step_id": "update", "tool": "update", "args": {"item_id": {"$ref": "find.id"}}}'
        "]}\n```\nLet me know if you need anything else."
    )
    plan = parse_model_plan(text, new_execution_id=_ids())
    assert plan["version"] == "1"
    assert plan["execution_id"] == "exec-1"
    assert plan["steps"][1]["depends_on"] == ["find"]

    calls = []
    result = DeclarativePlanInterpreter(
        {"lookup": lambda args: {"id": "item-7", "big": "x"},
         "update": lambda args: calls.append(args) or {"ok": True}},
        lambda tool, args: "allow",
    ).execute(plan)
    assert result.status == "completed"
    assert calls == [{"item_id": "item-7"}]


def test_integer_version_and_unknown_keys_are_repaired_not_trusted():
    plan = parse_model_plan(
        '{"version": 1, "reasoning": "because", "execution_id": "e",'
        ' "steps": [{"step_id": "a", "tool": "lookup", "args": {}, "note": "x"}]}',
        new_execution_id=_ids(),
    )
    assert plan == {
        "version": "1",
        "execution_id": "e",
        "steps": [{"step_id": "a", "tool": "lookup", "args": {}, "depends_on": [],
                   "output_fields": None}],
    }


def test_reference_to_unknown_step_is_still_rejected():
    with pytest.raises(PlanValidationError):
        parse_model_plan(
            '{"steps": [{"step_id": "a", "tool": "lookup",'
            ' "args": {"x": {"$ref": "ghost.id"}}}]}',
            new_execution_id=_ids(),
        )


def test_reference_to_later_step_is_still_rejected():
    with pytest.raises(PlanValidationError):
        parse_model_plan(
            '{"steps": ['
            '{"step_id": "a", "tool": "lookup", "args": {"x": {"$ref": "b.id"}}},'
            '{"step_id": "b", "tool": "lookup", "args": {}}]}',
            new_execution_id=_ids(),
        )


@pytest.mark.parametrize("text", ["", "no json here", "[1, 2, 3]", "{not json"])
def test_output_without_a_plan_object_is_rejected(text):
    with pytest.raises(PlanValidationError):
        parse_model_plan(text, new_execution_id=_ids())


def test_empty_steps_still_rejected():
    with pytest.raises(PlanValidationError):
        parse_model_plan('{"steps": []}', new_execution_id=_ids())


def test_unregistered_tool_later_in_plan_blocks_before_any_side_effect():
    calls = []
    result = DeclarativePlanInterpreter(
        {"lookup": lambda args: calls.append(args) or {"ok": True}},
        lambda tool, args: "allow",
    ).execute({"version": "1", "execution_id": "x", "steps": [
        {"step_id": "first", "tool": "lookup", "args": {}},
        {"step_id": "second", "tool": "unregistered_tool", "args": {}},
    ]})
    assert result.status == "blocked"
    assert calls == []
    assert [(s.step_id, s.error) for s in result.steps] == [("second", "tool_not_allowlisted")]
