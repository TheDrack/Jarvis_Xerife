from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers import mobile_sessions
from app.core.nexus import nexus


class FakeResponse:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.operation = None
        self.payload = None
        self.filters = {}

    def insert(self, payload):
        self.operation, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.operation, self.payload = "update", payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def execute(self):
        if self.operation == "insert":
            self.client.inserted.append(self.payload)
            return FakeResponse([self.payload])
        if self.operation == "update":
            self.client.updated.append((self.payload, dict(self.filters)))
            return FakeResponse([])
        raise AssertionError("Unexpected fake database operation")


class FakeRpc:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.rpc_calls.append((self.name, self.params))
        if self.name == "revoke_jarvis_mobile_session":
            return FakeResponse(True)
        if self.client.rpc_data is None:
            return FakeResponse([])
        return FakeResponse([self.client.rpc_data])


class FakeSupabase:
    def __init__(self):
        self.inserted = []
        self.updated = []
        self.rpc_calls = []
        self.rpc_data = {
            "user_id": "user-42",
            "username": "felipe@example.com",
            "email": "felipe@example.com",
            "full_name": "Felipe",
            "family_id": "b8e6b3aa-6c56-4e92-90c8-2f5f7e7dca12",
        }

    def table(self, name):
        assert name == mobile_sessions.SESSION_TABLE
        return FakeQuery(self, name)

    def rpc(self, name, params):
        assert name in {"rotate_jarvis_mobile_session", "revoke_jarvis_mobile_session"}
        return FakeRpc(self, name, params)


class FakeAuth:
    def authenticate_user(self, username, password):
        if username == "felipe@example.com" and password == "correct":
            return {
                "username": username,
                "email": username,
                "full_name": "Felipe",
                "user_id": "user-42",
            }
        return None

    def create_access_token(self, data, expires_delta=None):
        assert expires_delta == 15
        self.claims = data
        return "test-access-token"


def _client(monkeypatch, database=None):
    auth = FakeAuth()
    monkeypatch.setattr(nexus, "resolve", lambda name: auth if name == "auth_adapter" else None)
    monkeypatch.setattr(mobile_sessions, "get_supabase_admin_client", lambda: database)
    app = FastAPI()
    app.include_router(mobile_sessions.create_mobile_sessions_router())
    return TestClient(app), auth


def test_mobile_login_creates_hashed_refresh_token_and_short_access_token(monkeypatch):
    database = FakeSupabase()
    client, auth = _client(monkeypatch, database)

    response = client.post(
        "/v1/mobile/session/login",
        json={
            "username": "felipe@example.com",
            "password": "correct",
            "device_id": "android-1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    assert len(payload["refresh_token"]) >= 32
    assert database.inserted[0]["token_hash"] == sha256(
        payload["refresh_token"].encode()
    ).hexdigest()
    assert payload["refresh_token"] not in str(database.inserted[0])
    assert database.inserted[0]["device_id"] == "android-1"
    assert UUID(database.inserted[0]["family_id"])
    assert auth.claims["client"] == "jarvis-mobile"
    assert auth.claims["user_id"] == "user-42"
    assert auth.claims["device_id"] == "android-1"


def test_mobile_login_rejects_invalid_credentials(monkeypatch):
    database = FakeSupabase()
    client, _ = _client(monkeypatch, database)

    response = client.post(
        "/v1/mobile/session/login",
        json={
            "username": "felipe@example.com",
            "password": "wrong",
            "device_id": "android-1",
        },
    )

    assert response.status_code == 401
    assert database.inserted == []


def test_mobile_login_fails_closed_without_server_only_database_key(monkeypatch):
    client, _ = _client(monkeypatch, None)

    response = client.post(
        "/v1/mobile/session/login",
        json={
            "username": "felipe@example.com",
            "password": "correct",
            "device_id": "android-1",
        },
    )

    assert response.status_code == 503


def test_refresh_rotates_token_hash_and_returns_new_pair(monkeypatch):
    database = FakeSupabase()
    client, auth = _client(monkeypatch, database)
    old_token = "old-refresh-token-that-is-long-enough-for-validation"

    response = client.post(
        "/v1/mobile/session/refresh",
        json={"refresh_token": old_token, "device_id": "android-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "test-access-token"
    assert payload["refresh_token"] != old_token
    rpc_name, args = database.rpc_calls[0]
    assert rpc_name == "rotate_jarvis_mobile_session"
    assert args["p_token_hash"] == sha256(old_token.encode()).hexdigest()
    assert args["p_replacement_hash"] == sha256(payload["refresh_token"].encode()).hexdigest()
    assert args["p_device_id"] == "android-1"
    assert auth.claims["sid"] == database.rpc_data["family_id"]


def test_refresh_rejects_expired_revoked_or_unknown_token(monkeypatch):
    database = FakeSupabase()
    database.rpc_data = None
    client, _ = _client(monkeypatch, database)

    response = client.post(
        "/v1/mobile/session/refresh",
        json={
            "refresh_token": "unknown-refresh-token-that-is-long-enough",
            "device_id": "android-1",
        },
    )

    assert response.status_code == 401


def test_revoke_hashes_token_and_scopes_to_device(monkeypatch):
    database = FakeSupabase()
    client, _ = _client(monkeypatch, database)
    token = "refresh-token-to-revoke-that-is-long-enough"

    response = client.post(
        "/v1/mobile/session/revoke",
        json={"refresh_token": token, "device_id": "android-1"},
    )

    assert response.status_code == 204
    rpc_name, args = database.rpc_calls[0]
    assert rpc_name == "revoke_jarvis_mobile_session"
    assert args == {
        "p_token_hash": sha256(token.encode()).hexdigest(),
        "p_device_id": "android-1",
    }



def test_refresh_rotation_migration_qualifies_family_id_output_column():
    migration = (
        Path(__file__).resolve().parents[3]
        / "supabase"
        / "migrations"
        / "20261029170000_fix_mobile_session_rotation_ambiguity.sql"
    )
    sql = migration.read_text(encoding="utf-8")

    assert "update public.jarvis_mobile_device_sessions as s" in sql
    assert "where s.family_id = v_session.family_id;" in sql
    assert "where family_id = v_session.family_id;" not in sql
