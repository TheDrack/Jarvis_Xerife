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
