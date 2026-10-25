from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.adapters.infrastructure.routers import admin_recovery


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class FakeClient:
    def __init__(self, rows=None):
        self.query = FakeQuery(rows if rows is not None else [{"id": 1}])

    def table(self, name):
        assert name == "user"
        return self.query


@pytest.mark.asyncio
async def test_admin_recovery_requires_configured_token(monkeypatch):
    monkeypatch.delenv("JARVIS_ADMIN_RESET_TOKEN", raising=False)
    endpoint = admin_recovery.create_admin_recovery_router().routes[0].endpoint
    with pytest.raises(HTTPException) as exc:
        await endpoint(
            admin_recovery.AdminPasswordResetRequest(new_password="temporary-password-123456"),
            x_jarvis_reset_token="anything",
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_recovery_updates_only_admin_account(monkeypatch):
    monkeypatch.setenv("JARVIS_ADMIN_RESET_TOKEN", "test-reset-token")
    client = FakeClient()
    monkeypatch.setattr(admin_recovery, "get_supabase_admin_client", lambda: client)
    monkeypatch.setattr(
        admin_recovery.AuthAdapter,
        "get_password_hash",
        lambda self, password: "hashed:" + password,
    )
    endpoint = admin_recovery.create_admin_recovery_router().routes[0].endpoint
    await endpoint(
        admin_recovery.AdminPasswordResetRequest(new_password="temporary-password-123456"),
        x_jarvis_reset_token="test-reset-token",
    )
    assert ("username", "admin") in client.query.filters
    assert ("email", "admin@jarvis.ai") in client.query.filters
    assert client.query.payload["hashed_password"] == "hashed:temporary-password-123456"
    assert client.query.payload["disabled"] is False


@pytest.mark.asyncio
async def test_admin_recovery_fails_if_admin_row_missing(monkeypatch):
    monkeypatch.setenv("JARVIS_ADMIN_RESET_TOKEN", "test-reset-token")
    client = FakeClient(rows=[])
    monkeypatch.setattr(admin_recovery, "get_supabase_admin_client", lambda: client)
    endpoint = admin_recovery.create_admin_recovery_router().routes[0].endpoint
    with pytest.raises(HTTPException) as exc:
        await endpoint(
            admin_recovery.AdminPasswordResetRequest(new_password="temporary-password-123456"),
            x_jarvis_reset_token="test-reset-token",
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_recovery_logs_connection_metadata_without_exception_message(monkeypatch, caplog):
    import logging
    import socket

    monkeypatch.setenv("JARVIS_ADMIN_RESET_TOKEN", "unit-test-reset-value")

    class BrokenClient:
        def table(self, name):
            raise RuntimeError("do-not-log-this-message") from socket.gaierror(-2, "dns failure detail")

    monkeypatch.setattr(admin_recovery, "get_supabase_admin_client", lambda: BrokenClient())
    monkeypatch.setattr(admin_recovery.settings, "supabase_url", "https://project.example.supabase.co")

    endpoint = admin_recovery.create_admin_recovery_router().routes[0].endpoint
    with caplog.at_level(logging.ERROR, logger=admin_recovery.__name__):
        with pytest.raises(HTTPException) as exc:
            await endpoint(
                admin_recovery.AdminPasswordResetRequest(new_password="unit-test-password-long-enough-123"),
                x_jarvis_reset_token="unit-test-reset-value",
            )

    assert exc.value.status_code == 503
    assert "RuntimeError -> gaierror" in caplog.text
    assert "project.example.supabase.co" in caplog.text
    assert "dns_errno=-2" in caplog.text
    assert "do-not-log-this-message" not in caplog.text
    assert "dns failure detail" not in caplog.text
    assert "unit-test-reset-value" not in caplog.text
    assert "unit-test-password-long-enough-123" not in caplog.text
