from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from app.adapters.infrastructure.agent_worker_credentials import (
    AgentWorkerCredentialStore,
)


def _store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("""
            create table jarvis_agents (
                agent_id text primary key,
                runtime_version text not null,
                status text not null
            )
        """))
        connection.execute(text("""
            create table jarvis_agent_credentials (
                credential_id text primary key,
                agent_id text not null,
                principal_id text not null,
                token_hash text not null unique,
                available_tools text not null,
                created_at datetime not null,
                expires_at datetime not null,
                last_used_at datetime,
                revoked_at datetime
            )
        """))
    return engine, AgentWorkerCredentialStore(engine)


def test_issue_stores_only_a_hash_and_registers_the_agent():
    engine, store = _store()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=2)

    token = store.issue(
        agent_id="mini-worker-1",
        principal_id="worker:mini-worker-1",
        available_tools=["text_reasoning"],
        expires_at=expires_at,
    )

    assert token.startswith("jarvisw_")
    with engine.connect() as connection:
        credential = connection.execute(text(
            "select token_hash, available_tools from jarvis_agent_credentials"
        )).mappings().one()
        agent = connection.execute(text(
            "select agent_id, status from jarvis_agents"
        )).mappings().one()

    assert credential["token_hash"] != token
    assert len(credential["token_hash"]) == 64
    assert json.loads(credential["available_tools"]) == ["text_reasoning"]
    assert dict(agent) == {"agent_id": "mini-worker-1", "status": "offline"}


def test_authenticate_resolves_server_side_agent_identity_and_capabilities():
    _, store = _store()
    token = store.issue(
        agent_id="mini-worker-2",
        principal_id="worker:mini-worker-2",
        available_tools=["text_reasoning"],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    principal = store.authenticate(token)

    assert principal is not None
    assert principal.agent_id == "mini-worker-2"
    assert principal.principal_id == "worker:mini-worker-2"
    assert principal.available_tools == ("text_reasoning",)


def test_authenticate_rejects_unknown_expired_and_revoked_tokens():
    engine, store = _store()
    expired = store.issue(
        agent_id="expired-worker",
        principal_id="worker:expired-worker",
        available_tools=["text_reasoning"],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    with engine.begin() as connection:
        connection.execute(
            text("update jarvis_agent_credentials set expires_at = :expired where token_hash = :token_hash"),
            {
                "expired": datetime.now(timezone.utc) - timedelta(seconds=1),
                "token_hash": store._token_hash(expired),
            },
        )
    revoked = store.issue(
        agent_id="revoked-worker",
        principal_id="worker:revoked-worker",
        available_tools=["text_reasoning"],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    store.revoke_agent("revoked-worker")

    assert store.authenticate("jarvisw_unknown") is None
    assert store.authenticate(expired) is None
    assert store.authenticate(revoked) is None


def test_issue_rejects_unattested_capabilities():
    _, store = _store()

    try:
        store.issue(
            agent_id="mini-worker-3",
            principal_id="worker:mini-worker-3",
            available_tools=["text_reasoning", "shell_execute"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    except ValueError as exc:
        assert "unsupported worker capabilities" in str(exc)
    else:
        raise AssertionError("unattested capabilities must not be provisioned")



def test_issuing_replacement_credential_revokes_the_previous_token():
    _, store = _store()
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    first = store.issue(
        agent_id="rotating-worker",
        principal_id="worker:rotating-worker",
        available_tools=["text_reasoning"],
        expires_at=expiry,
    )
    second = store.issue(
        agent_id="rotating-worker",
        principal_id="worker:rotating-worker",
        available_tools=["text_reasoning"],
        expires_at=expiry,
    )

    assert first != second
    assert store.authenticate(first) is None
    assert store.authenticate(second) is not None
