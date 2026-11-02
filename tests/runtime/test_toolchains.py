"""Tests for typed DAG toolchains and explicit result bindings."""

from threading import Event

import pytest

from app.runtime.toolbox import (
    ToolchainManifest,
    ToolchainRunner,
    ToolRegistry,
    ToolResult,
)


def make_chain(**overrides):
    payload = {
        "toolchain_id": "sample.chain",
        "version": "1.0.0",
        "description": "Sample DAG",
        "steps": [
            {
                "step_id": "notify",
                "tool_id": "sample.write",
                "depends_on": ["fetch"],
                "bindings": {"text": "steps.fetch.output.message"},
            },
            {
                "step_id": "fetch",
                "tool_id": "sample.read",
                "arguments": {"key": "status"},
            },
        ],
    }
    payload.update(overrides)
    return ToolchainManifest.model_validate(payload)


class RecordingDispatcher:
    def __init__(self, fail_tools=None):
        self.calls = []
        self.fail_tools = set(fail_tools or [])

    def dispatch(self, request):
        self.calls.append(request)
        failed = request.tool_id in self.fail_tools
        return ToolResult(
            tool_id=request.tool_id,
            request_id=request.request_id,
            success=not failed,
            status="failed" if failed else "succeeded",
            output=(
                None
                if failed
                else (
                    {"message": "status atualizado"}
                    if request.tool_id == "sample.read"
                    else {"sent": request.arguments.get("text")}
                )
            ),
            error_code="provider_error" if failed else None,
        )


def test_manifest_topologically_orders_steps():
    chain = make_chain()
    assert [step.step_id for step in chain.topological_order()] == [
        "fetch",
        "notify",
    ]


def test_manifest_rejects_dependency_cycle():
    with pytest.raises(ValueError, match="cíclica"):
        make_chain(
            steps=[
                {"step_id": "a", "tool_id": "sample.a", "depends_on": ["b"]},
                {"step_id": "b", "tool_id": "sample.b", "depends_on": ["a"]},
            ]
        )


def test_manifest_rejects_missing_dependency():
    with pytest.raises(ValueError, match="inexistentes"):
        make_chain(
            steps=[
                {
                    "step_id": "a",
                    "tool_id": "sample.a",
                    "depends_on": ["missing"],
                },
            ]
        )


def test_binding_requires_declared_dependency():
    with pytest.raises(ValueError, match="depends_on"):
        make_chain(
            steps=[
                {"step_id": "a", "tool_id": "sample.a"},
                {
                    "step_id": "b",
                    "tool_id": "sample.b",
                    "bindings": {"value": "steps.a.output.value"},
                },
            ]
        )


def test_runner_executes_dependencies_and_resolves_bindings():
    dispatcher = RecordingDispatcher()
    result = ToolchainRunner(dispatcher).run(make_chain())

    assert result.status == "succeeded"
    assert result.success is True
    assert [call.tool_id for call in dispatcher.calls] == [
        "sample.read",
        "sample.write",
    ]
    assert dispatcher.calls[1].arguments == {"text": "status atualizado"}


def test_failed_dependency_skips_dependent_step():
    chain = make_chain(
        steps=[
            {"step_id": "fetch", "tool_id": "sample.read"},
            {
                "step_id": "notify",
                "tool_id": "sample.write",
                "depends_on": ["fetch"],
                "bindings": {"text": "steps.fetch.output.message"},
            },
        ]
    )
    dispatcher = RecordingDispatcher(fail_tools={"sample.read"})
    result = ToolchainRunner(dispatcher).run(chain)

    assert result.status == "failed"
    assert [call.tool_id for call in dispatcher.calls] == ["sample.read"]
    assert result.step_results["notify"].error_code == "dependency_failed"


def test_continue_on_error_runs_independent_steps_only():
    chain = make_chain(
        continue_on_error=True,
        steps=[
            {"step_id": "first", "tool_id": "sample.read"},
            {"step_id": "independent", "tool_id": "sample.independent"},
            {
                "step_id": "dependent",
                "tool_id": "sample.write",
                "depends_on": ["first"],
            },
        ],
    )
    dispatcher = RecordingDispatcher(fail_tools={"sample.read"})
    result = ToolchainRunner(dispatcher).run(chain)

    assert result.status == "partial"
    assert [call.tool_id for call in dispatcher.calls] == [
        "sample.read",
        "sample.independent",
    ]
    assert result.step_results["dependent"].error_code == "dependency_failed"


def test_cancel_event_stops_pending_steps():
    dispatcher = RecordingDispatcher()
    cancel = Event()
    cancel.set()
    result = ToolchainRunner(dispatcher).run(make_chain(), cancel_event=cancel)

    assert result.status == "cancelled"
    assert dispatcher.calls == []
    assert all(
        step.error_code == "toolchain_cancelled"
        for step in result.step_results.values()
    )


def test_checked_in_toolchain_manifest_is_loadable():
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "toolchains"
        / "telegram_notification.json"
    )
    chain = ToolchainManifest.from_file(path)
    assert chain.toolchain_id == "communication.telegram_notification"
    assert chain.steps[0].tool_id == "telegram.send_message"


def test_toolchain_never_retries_active_side_effects_automatically():
    registry = ToolRegistry(
        [
            {
                "tool_id": "sample.write",
                "version": "1.0.0",
                "description": "Write",
                "capability": "sample.write",
                "adapter_id": "sample",
                "operation": "write",
                "authorization_capability": "sample",
                "input_schema": {"type": "object"},
                "risk_level": "active",
                "idempotency_mode": "process",
                "requires_idempotency_key": True,
            }
        ]
    )

    class RetryableSideEffectDispatcher:
        def __init__(self):
            self.registry = registry
            self.calls = 0

        def dispatch(self, request):
            self.calls += 1
            return ToolResult(
                tool_id=request.tool_id,
                request_id=request.request_id,
                success=False,
                status="failed",
                retryable=True,
            )

    dispatcher = RetryableSideEffectDispatcher()
    chain = ToolchainManifest.model_validate(
        {
            "toolchain_id": "retry.active",
            "version": "1.0.0",
            "description": "Active tools must not be blindly retried",
            "steps": [
                {
                    "step_id": "write",
                    "tool_id": "sample.write",
                    "max_attempts": 5,
                }
            ],
        }
    )
    result = ToolchainRunner(dispatcher).run(
        chain,
        approvals={
            "write": {
                "approval_id": "test-approved-operation",
                "idempotency_key": "active-no-retry",
            }
        },
    )

    assert result.status == "failed"
    assert dispatcher.calls == 1
