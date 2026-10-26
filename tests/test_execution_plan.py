"""Tests for the bounded declarative plan interpreter."""
import pytest
from app.multiagent.execution_plan import DeclarativePlanInterpreter, PlanValidationError, validate_plan

def make_plan(*steps):
    return {"version": "1", "execution_id": "exec-1", "steps": list(steps)}


def make_step(step_id, tool="lookup", args=None, **extra):
    return {"step_id": step_id, "tool": tool, "args": args or {}, **extra}


def allow_all(_tool, _args):
    return "allow"


def test_references_use_only_projected_payload():
    calls = []
    interpreter = DeclarativePlanInterpreter(
        {"lookup": lambda args: {"id": "item-7", "large": "ignored"},
         "update": lambda args: calls.append(args) or {"updated": True}},
        allow_all,
    )
    result = interpreter.execute(make_plan(
        make_step("find", output_fields=["id"]),
        make_step("update", tool="update", args={"item_id": {"$ref": "find.id"}}, depends_on=["find"]),
    ))
    assert result.status == "completed"
    assert calls == [{"item_id": "item-7"}]


@pytest.mark.parametrize("bad_plan", [
    {"version": "1", "execution_id": "x", "steps": []},
    {"version": "2", "execution_id": "x", "steps": [{"step_id": "a", "tool": "lookup", "args": {}}]},
    {"version": "1", "execution_id": "x", "extra": True, "steps": [{"step_id": "a", "tool": "lookup", "args": {}}]},
    make_plan(make_step("a"), make_step("a")),
    make_plan(make_step("a", depends_on=["future"]), make_step("future")),
])
def test_invalid_plan_rejected_before_dispatch(bad_plan):
    calls = []
    interpreter = DeclarativePlanInterpreter({"lookup": lambda args: calls.append(args)}, allow_all)
    with pytest.raises(PlanValidationError):
        interpreter.execute(bad_plan)
    assert calls == []


def test_unregistered_tool_is_blocked():
    result = DeclarativePlanInterpreter({}, allow_all).execute(make_plan(make_step("a", "unregistered_tool")))
    assert result.status == "blocked"
    assert result.steps[0].error == "tool_not_allowlisted"


def test_policy_denial_stops_plan():
    calls = []
    policy_calls = []

    def policy(tool, args):
        policy_calls.append(tool)
        return "deny" if tool == "mutate" else "allow"

    interpreter = DeclarativePlanInterpreter(
        {"lookup": lambda args: {"id": 1}, "mutate": lambda args: calls.append(args)},
        policy,
    )
    result = interpreter.execute(make_plan(make_step("read"), make_step("write", "mutate", depends_on=["read"])))
    assert result.status == "blocked"
    assert policy_calls == ["lookup", "mutate"]
    assert calls == []


def test_approval_pauses_before_dispatch():
    calls = []
    interpreter = DeclarativePlanInterpreter(
        {"mutate": lambda args: calls.append("mutate"), "lookup": lambda args: calls.append("lookup")},
        lambda tool, args: "approval_required" if tool == "mutate" else "allow",
    )
    result = interpreter.execute(make_plan(make_step("first", "mutate"), make_step("second", "lookup")))
    assert result.status == "approval_required"
    assert calls == []
    assert len(result.steps) == 1


def test_connector_exception_is_unknown_and_never_retried():
    calls = []

    def flaky(_args):
        calls.append("called")
        raise TimeoutError("operation outcome uncertain")

    result = DeclarativePlanInterpreter({"mutate": flaky}, allow_all).execute(make_plan(make_step("a", "mutate")))
    assert result.status == "unknown"
    assert result.steps[0].status == "unknown"
    assert result.steps[0].error == "TimeoutError"
    assert calls == ["called"]


def test_bad_reference_blocks_downstream_step():
    calls = []
    interpreter = DeclarativePlanInterpreter(
        {"lookup": lambda args: {"id": 1}, "update": lambda args: calls.append(args)},
        allow_all,
    )
    result = interpreter.execute(make_plan(
        make_step("read"),
        make_step("write", "update", {"id": {"$ref": "read.missing"}}, depends_on=["read"]),
    ))
    assert result.status == "blocked"
    assert calls == []


def test_oversized_plan_rejected():
    oversized = make_plan(make_step("a", args={"text": "x" * 500}))
    with pytest.raises(PlanValidationError):
        validate_plan(oversized, max_plan_bytes=100)


def test_reference_requires_explicit_dependency():
    candidate = make_plan(
        make_step("read"),
        make_step("write", "update", {"id": {"$ref": "read.id"}}),
    )
    with pytest.raises(PlanValidationError, match="depends_on"):
        validate_plan(candidate)


def test_policy_error_fails_closed_before_tool_call():
    calls = []
    interpreter = DeclarativePlanInterpreter(
        {"mutate": lambda args: calls.append(args)},
        lambda _tool, _args: (_ for _ in ()).throw(RuntimeError("policy unavailable")),
    )
    result = interpreter.execute(make_plan(make_step("write", "mutate")))
    assert result.status == "blocked"
    assert result.steps[0].error == "policy_unavailable"
    assert calls == []


def test_plan_rejects_python_values_that_json_would_coerce():
    candidate = make_plan(make_step("read", args={1: "not a JSON object key"}))
    with pytest.raises(PlanValidationError, match="keys must be strings"):
        validate_plan(candidate)


def test_cyclic_python_input_is_rejected_cleanly():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(PlanValidationError):
        validate_plan(make_plan(make_step("read", args={"loop": cyclic})))


def test_execution_budget_stops_before_dispatching_next_step(monkeypatch):
    import app.multiagent.execution_plan as execution_plan

    ticks = iter([0.0, 0.0, 0.0, 0.001, 1.0])
    monkeypatch.setattr(execution_plan.time, "monotonic", lambda: next(ticks))
    calls = []
    interpreter = DeclarativePlanInterpreter(
        {"lookup": lambda args: calls.append(args) or {"ok": True}},
        allow_all,
        max_elapsed_seconds=0.5,
    )
    result = interpreter.execute(make_plan(make_step("first"), make_step("second")))
    assert result.status == "blocked"
    assert [step.status for step in result.steps] == ["completed", "blocked"]
    assert result.steps[-1].error == "execution_budget_exhausted"
    assert calls == [{}]


@pytest.mark.parametrize("invalid_budget", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_elapsed_budget_must_be_finite_and_positive(invalid_budget):
    with pytest.raises(ValueError, match="finite and positive"):
        DeclarativePlanInterpreter({}, allow_all, max_elapsed_seconds=invalid_budget)

def test_journal_failure_before_dispatch_fails_closed():
    calls = []
    def broken_journal(_event):
        raise OSError("storage unavailable")

    interpreter = DeclarativePlanInterpreter(
        {"mutate": lambda args: calls.append(args)},
        allow_all,
        event_sink=broken_journal,
    )
    result = interpreter.execute(make_plan(make_step("write", "mutate")))
    assert result.status == "blocked"
    assert result.steps[0].error == "journal_unavailable"
    assert calls == []


def test_journal_failure_after_side_effect_returns_unknown_without_retry():
    calls = []
    events = []

    def journal(event):
        events.append(event)
        if event["event"] == "step_finished":
            raise OSError("durable write failed")

    interpreter = DeclarativePlanInterpreter(
        {"mutate": lambda args: calls.append(args) or {"ok": True}},
        allow_all,
        event_sink=journal,
    )
    result = interpreter.execute(make_plan(make_step("write", "mutate")))
    assert result.status == "unknown"
    assert result.steps[0].error == "journal_unavailable"
    assert len(calls) == 1


def test_journal_failure_on_step_started_prevents_dispatch():
    calls = []

    def journal(event):
        if event["event"] == "step_started":
            raise OSError("journal unavailable")

    interpreter = DeclarativePlanInterpreter(
        {"mutate": lambda args: calls.append(args)},
        allow_all,
        event_sink=journal,
    )
    result = interpreter.execute(make_plan(make_step("write", "mutate")))
    assert result.status == "blocked"
    assert result.steps[0].error == "journal_unavailable"
    assert calls == []


def test_lifecycle_events_never_include_raw_args_or_result_payloads():
    events = []
    secret = "do-not-log-this-secret"
    interpreter = DeclarativePlanInterpreter(
        {"lookup": lambda args: {"token": secret, "ok": True}},
        allow_all,
        event_sink=events.append,
    )
    result = interpreter.execute(make_plan(make_step("read", args={"token": secret})))
    assert result.status == "completed"
    assert all("args" not in event and "result" not in event for event in events)
    assert secret not in repr(events)