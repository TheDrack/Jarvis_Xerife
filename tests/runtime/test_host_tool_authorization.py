"""Host-backed tool authorization policy tests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.toolbox import (
    HostToolAuthorizationPolicy,
    ToolAuthorizationDecision,
    ToolDispatcher,
    ToolManifest,
    ToolRegistry,
    ToolRequest,
)
from app.runtime.toolbox.host_authorization import (
    TrustedToolPrincipal,
    VerifiedToolApproval,
    tool_request_digest,
)


def _manifest(*, risk_level="read_only"):
    return ToolManifest(
        tool_id="sample.read" if risk_level == "read_only" else "sample.write",
        version="1.0.0",
        description="Authorization test tool",
        capability="sample.read" if risk_level == "read_only" else "sample.write",
        adapter_id="sample_adapter",
        operation="read" if risk_level == "read_only" else "write",
        authorization_capability="sample_adapter",
        risk_level=risk_level,
        allowed_scopes=("local", "account:*"),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )


def _principal(*, capabilities=("sample.read",), agent_id=None):
    return TrustedToolPrincipal(
        principal_id="user-1",
        session_id="session-1",
        capabilities=frozenset(capabilities),
        agent_id=agent_id,
    )


def test_read_only_authorization_uses_trusted_principal_not_request_caller():
    manifest = _manifest()
    request = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.read",
        caller="administrator",
        scope="local",
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal()
    )

    decision = policy.authorize_tool(request, manifest)

    assert decision.granted is True
    assert decision.principal_id == "user-1"
    assert decision.session_id == "session-1"
    assert decision.approval_id is None


def test_missing_trusted_principal_fails_closed():
    manifest = _manifest()
    request = ToolRequest(tool_id=manifest.tool_id, capability="sample.read")
    policy = HostToolAuthorizationPolicy(principal_resolver=lambda: None)

    with pytest.raises(PermissionError, match="authenticated principal"):
        policy.authorize_tool(request, manifest)


def test_untrusted_caller_cannot_supply_capability_or_identity():
    manifest = _manifest()
    request = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.read",
        caller="user-1",
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(capabilities=())
    )

    with pytest.raises(PermissionError, match="capability grant"):
        policy.authorize_tool(request, manifest)


def test_task_execution_requires_owner_and_current_worker_attempt():
    manifest = _manifest()
    request = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.read",
        task_id="task-1",
        attempt_id="attempt-1",
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(agent_id="worker-1"),
        task_owner_resolver=lambda task_id: "user-1",
        task_executor_resolver=lambda task_id, attempt_id: "worker-1",
    )

    decision = policy.authorize_tool(request, manifest)

    assert decision.granted is True
    assert decision.principal_id == "user-1"


@pytest.mark.parametrize(
    ("owner", "executor"),
    [("user-2", "worker-1"), ("user-1", "worker-2"), ("user-1", None)],
)
def test_cross_owner_or_stale_worker_attempt_is_denied(owner, executor):
    manifest = _manifest()
    request = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.read",
        task_id="task-1",
        attempt_id="attempt-1",
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(agent_id="worker-1"),
        task_owner_resolver=lambda task_id: owner,
        task_executor_resolver=lambda task_id, attempt_id: executor,
    )

    with pytest.raises(PermissionError):
        policy.authorize_tool(request, manifest)


def test_worker_cannot_dispatch_without_task_and_attempt_binding():
    manifest = _manifest()
    request = ToolRequest(tool_id=manifest.tool_id, capability="sample.read")
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(agent_id="worker-1"),
    )

    with pytest.raises(PermissionError, match="task and attempt"):
        policy.authorize_tool(request, manifest)


def test_active_tool_requires_verifiable_exact_request_approval():
    manifest = _manifest(risk_level="active")
    request = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.write",
        arguments={"value": "approved"},
        scope="local",
        approval_id="approval-1",
        task_id="task-1",
    )
    now = datetime.now(timezone.utc)
    approval = VerifiedToolApproval(
        approval_id="approval-1",
        status="approved",
        principal_id="user-1",
        session_id="session-1",
        task_id="task-1",
        tool_id=manifest.tool_id,
        tool_version=manifest.version,
        capability="sample.write",
        scope="local",
        operation=manifest.operation,
        arguments_digest=tool_request_digest(request),
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=2),
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(capabilities=("sample.write",)),
        task_owner_resolver=lambda task_id: "user-1",
        approval_verifier=lambda approval_id: approval,
        clock=lambda: now,
    )

    decision = policy.authorize_tool(request, manifest)

    assert decision.granted is True
    assert decision.approval_id == "approval-1"
    assert decision.expires_at == approval.expires_at


def test_active_tool_without_approval_verifier_fails_closed():
    manifest = _manifest(risk_level="active")
    request = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.write",
        approval_id="approval-1",
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(capabilities=("sample.write",))
    )

    with pytest.raises(PermissionError, match="approval verifier"):
        policy.authorize_tool(request, manifest)


def test_approval_cannot_be_replayed_with_changed_arguments_or_scope():
    manifest = _manifest(risk_level="active")
    original = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.write",
        arguments={"value": "approved"},
        scope="local",
        approval_id="approval-1",
    )
    now = datetime.now(timezone.utc)
    approval = VerifiedToolApproval(
        approval_id="approval-1",
        status="approved",
        principal_id="user-1",
        session_id="session-1",
        task_id=None,
        tool_id=manifest.tool_id,
        tool_version=manifest.version,
        capability="sample.write",
        scope="local",
        operation=manifest.operation,
        arguments_digest=tool_request_digest(original),
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=2),
    )
    changed = original.model_copy(
        update={"arguments": {"value": "different"}, "scope": "account:other"}
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(capabilities=("sample.write",)),
        approval_verifier=lambda approval_id: approval,
        clock=lambda: now,
    )

    with pytest.raises(PermissionError, match="does not match"):
        policy.authorize_tool(changed, manifest)


def test_expired_or_rejected_approval_is_denied():
    manifest = _manifest(risk_level="active")
    now = datetime.now(timezone.utc)
    request = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.write",
        approval_id="approval-1",
    )
    approval = VerifiedToolApproval(
        approval_id="approval-1",
        status="rejected",
        principal_id="user-1",
        session_id="session-1",
        task_id=None,
        tool_id=manifest.tool_id,
        tool_version=manifest.version,
        capability="sample.write",
        scope="local",
        operation=manifest.operation,
        arguments_digest=tool_request_digest(request),
        approved_at=now - timedelta(minutes=3),
        expires_at=now - timedelta(minutes=1),
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(capabilities=("sample.write",)),
        approval_verifier=lambda approval_id: approval,
        clock=lambda: now,
    )

    with pytest.raises(PermissionError):
        policy.authorize_tool(request, manifest)



def test_dispatcher_passes_task_binding_to_audit_after_host_authorization():
    manifest = _manifest()
    events = []
    dispatcher = ToolDispatcher(
        ToolRegistry([manifest]),
        resolver=lambda _: type("Adapter", (), {"read": lambda self: {"ok": True}})(),
        authorizer=HostToolAuthorizationPolicy(
            principal_resolver=lambda: _principal(agent_id="worker-1"),
            task_owner_resolver=lambda task_id: "user-1",
            task_executor_resolver=lambda task_id, attempt_id: "worker-1",
        ),
        event_sink=events.append,
    )

    result = dispatcher.dispatch(
        ToolRequest(
            tool_id=manifest.tool_id,
            capability="sample.read",
            task_id="task-1",
            attempt_id="attempt-1",
        )
    )

    assert result.success is True
    assert len(events) == 1
    assert events[0].task_id == "task-1"
    assert events[0].attempt_id == "attempt-1"
    assert events[0].principal_id == "user-1"


def test_dispatcher_rejects_authorization_decision_for_another_task():
    manifest = _manifest()
    resolved = []
    decision = ToolAuthorizationDecision(
        granted=True,
        principal_id="user-1",
        session_id="session-1",
        tool_id=manifest.tool_id,
        tool_version=manifest.version,
        capability="sample.read",
        scope="local",
        operation=manifest.operation,
        task_id="different-task",
        attempt_id="attempt-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )

    class MismatchedPolicy:
        def authorize_tool(self, request, selected_manifest):
            return decision

    dispatcher = ToolDispatcher(
        ToolRegistry([manifest]),
        resolver=lambda _: resolved.append("adapter"),
        authorizer=MismatchedPolicy(),
    )
    result = dispatcher.dispatch(
        ToolRequest(
            tool_id=manifest.tool_id,
            capability="sample.read",
            task_id="task-1",
            attempt_id="attempt-1",
        )
    )

    assert result.success is False
    assert result.error_code == "authorization_denied"
    assert resolved == []



def test_approval_cannot_be_replayed_with_a_different_idempotency_key():
    manifest = _manifest(risk_level="active")
    now = datetime.now(timezone.utc)
    original = ToolRequest(
        tool_id=manifest.tool_id,
        capability="sample.write",
        arguments={"value": "same-effect"},
        scope="local",
        approval_id="approval-1",
        idempotency_key="intent-1",
    )
    approval = VerifiedToolApproval(
        approval_id="approval-1",
        status="approved",
        principal_id="user-1",
        session_id="session-1",
        task_id=None,
        tool_id=manifest.tool_id,
        tool_version=manifest.version,
        capability="sample.write",
        scope="local",
        operation=manifest.operation,
        arguments_digest=tool_request_digest(original),
        approved_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(minutes=2),
    )
    policy = HostToolAuthorizationPolicy(
        principal_resolver=lambda: _principal(capabilities=("sample.write",)),
        approval_verifier=lambda approval_id: approval,
        clock=lambda: now,
    )

    with pytest.raises(PermissionError, match="does not match"):
        policy.authorize_tool(
            original.model_copy(update={"idempotency_key": "intent-2"}),
            manifest,
        )



def test_dispatcher_idempotency_namespace_isolated_between_owned_tasks():
    manifest = _manifest(risk_level="active")
    now = datetime.now(timezone.utc)
    requests = [
        ToolRequest(
            tool_id=manifest.tool_id,
            capability="sample.write",
            task_id=task_id,
            approval_id=f"approval-{task_id}",
            idempotency_key="same-key",
        )
        for task_id in ("task-a", "task-b")
    ]
    approvals = {
        request.approval_id: VerifiedToolApproval(
            approval_id=request.approval_id,
            status="approved",
            principal_id="user-1",
            session_id="session-1",
            task_id=request.task_id,
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            capability="sample.write",
            scope="local",
            operation=manifest.operation,
            arguments_digest=tool_request_digest(request),
            approved_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(minutes=2),
        )
        for request in requests
    }
    calls = []

    class Adapter:
        def write(self):
            calls.append("write")
            return {"ok": True}

    dispatcher = ToolDispatcher(
        ToolRegistry([manifest]),
        resolver=lambda _: Adapter(),
        authorizer=HostToolAuthorizationPolicy(
            principal_resolver=lambda: _principal(capabilities=("sample.write",)),
            task_owner_resolver=lambda task_id: "user-1",
            approval_verifier=lambda approval_id: approvals.get(approval_id),
            clock=lambda: now,
        ),
    )

    results = [dispatcher.dispatch(request) for request in requests]

    assert all(result.success for result in results)
    assert calls == ["write", "write"]
