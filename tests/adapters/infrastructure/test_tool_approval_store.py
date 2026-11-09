from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.adapters.infrastructure.tool_approval_store import ToolApprovalStore


def _store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("""
            create table jarvis_tool_approvals (
                approval_id text primary key, principal_id text not null, task_id text,
                tool_id text not null, tool_version text not null, capability text not null,
                scope text not null, operation text not null, arguments_digest text not null,
                idempotency_key text, status text not null, approver_session_id text,
                created_at datetime not null, approved_at datetime, expires_at datetime not null,
                revoked_at datetime, consumed_at datetime, consumed_by text
            )
        """))
    return engine, ToolApprovalStore(engine)


def _pending(store, *, task_id="task-1", digest="a" * 64):
    return store.create_pending(
        principal_id="user-1", task_id=task_id, tool_id="sample.write",
        tool_version="1.2.3", capability="sample.write", scope="account:primary",
        operation="write", arguments_digest=digest, idempotency_key="intent-1",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )


def _consume(store, approval_id, **overrides):
    args = {
        "principal_id": "user-1", "task_id": "task-1", "tool_id": "sample.write",
        "tool_version": "1.2.3", "capability": "sample.write",
        "scope": "account:primary", "operation": "write",
        "arguments_digest": "a" * 64, "idempotency_key": "intent-1",
        "executor_id": "worker:mini-1",
    }
    args.update(overrides)
    return store.consume(approval_id, **args)


def test_pending_approval_never_authorizes_until_explicitly_approved():
    _, store = _store()
    approval_id = _pending(store)
    assert _consume(store, approval_id) is None
    assert store.approve(approval_id, principal_id="user-1", approver_session_id="user-session-1")
    consumed = _consume(store, approval_id)
    assert consumed is not None
    assert consumed["status"] == "consumed"
    assert consumed["approver_session_id"] == "user-session-1"
    assert consumed["consumed_by"] == "worker:mini-1"


def test_approval_is_single_use_across_repeated_consumption():
    _, store = _store()
    approval_id = _pending(store)
    assert store.approve(approval_id, principal_id="user-1", approver_session_id="user-session-1")
    assert _consume(store, approval_id) is not None
    assert _consume(store, approval_id) is None


@pytest.mark.parametrize("override", [
    {"principal_id": "user-2"}, {"task_id": "task-2"},
    {"tool_id": "sample.delete"}, {"tool_version": "9.9.9"},
    {"capability": "admin"}, {"scope": "account:other"},
    {"operation": "delete"}, {"arguments_digest": "b" * 64},
    {"idempotency_key": "other-intent"},
])
def test_approval_cannot_be_consumed_for_changed_intent(override):
    _, store = _store()
    approval_id = _pending(store)
    assert store.approve(approval_id, principal_id="user-1", approver_session_id="user-session-1")
    assert _consume(store, approval_id, **override) is None


def test_only_owner_can_approve_or_revoke_pending_intent():
    _, store = _store()
    approval_id = _pending(store)
    assert not store.approve(approval_id, principal_id="user-2", approver_session_id="other-session")
    assert not store.revoke(approval_id, principal_id="user-2")
    assert store.revoke(approval_id, principal_id="user-1")
    assert not store.approve(approval_id, principal_id="user-1", approver_session_id="user-session-1")


def test_expired_approval_cannot_be_approved_or_consumed():
    engine, store = _store()
    approval_id = _pending(store)
    with engine.begin() as connection:
        connection.execute(
            text("update jarvis_tool_approvals set expires_at = :expiry where approval_id = :id"),
            {"expiry": datetime.now(timezone.utc) - timedelta(seconds=1), "id": approval_id},
        )
    assert not store.approve(approval_id, principal_id="user-1", approver_session_id="user-session-1")
    assert _consume(store, approval_id) is None


def test_pending_approval_rejects_invalid_intent_and_expiry():
    _, store = _store()
    with pytest.raises(ValueError, match="semantic version"):
        store.create_pending(
            principal_id="user-1", task_id=None, tool_id="sample.write",
            tool_version="latest", capability="sample.write", scope="local",
            operation="write", arguments_digest="a" * 64, idempotency_key=None,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
    with pytest.raises(ValueError, match="24 hours"):
        store.create_pending(
            principal_id="user-1", task_id=None, tool_id="sample.write",
            tool_version="1.2.3", capability="sample.write", scope="local",
            operation="write", arguments_digest="a" * 64, idempotency_key=None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=2),
        )
