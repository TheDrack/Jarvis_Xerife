from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers import environment_observations as module
from app.core.nexus import nexus


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, database):
        self.database = database
        self.operation = "select"
        self.payload = None
        self.filters = {}
        self.limit_count = None
        self.order_key = None
        self.descending = False

    def select(self, *_args):
        if self.operation != "insert":
            self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, key, desc=False):
        self.order_key = key
        self.descending = desc
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def execute(self):
        if self.operation == "insert":
            unique = (self.payload["user_id"], self.payload["request_id"])
            if any((row["user_id"], row["request_id"]) == unique for row in self.database.rows):
                raise RuntimeError("unique constraint")
            self.database.rows.append(dict(self.payload))
            return Result([dict(self.payload)])
        rows = [
            dict(row) for row in self.database.rows
            if all(row.get(key) == value for key, value in self.filters.items())
        ]
        if self.order_key:
            rows.sort(key=lambda row: row.get(self.order_key, ""), reverse=self.descending)
        if self.limit_count is not None:
            rows = rows[:self.limit_count]
        return Result(rows)


class Database:
    def __init__(self):
        self.rows = []

    def table(self, name):
        assert name == module.TABLE
        return Query(self)


class Auth:
    def verify_token(self, token):
        if token != "valid":
            return None
        return {
            "sub": "user@example.test",
            "user_id": "user-1",
            **self.extra_claims,
        }


def make_client(monkeypatch, database=None, claims=None):
    auth = Auth()
    auth.extra_claims = claims or {}
    monkeypatch.setattr(nexus, "resolve", lambda name: auth if name == "auth_adapter" else None)
    monkeypatch.setattr(module, "get_supabase_admin_client", lambda: database)

    async def current_user():
        return SimpleNamespace(username="user@example.test", user_id="user-1")

    app = FastAPI()
    app.include_router(module.create_environment_observations_router(current_user))
    return TestClient(app)


def observation(**overrides):
    body = {
        "device_id": "desktop-main",
        "source_device_type": "desktop",
        "observation_type": "network_snapshot",
        "schema_version": 1,
        "request_id": str(uuid4()),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"interfaces": [], "neighbors": [], "platform": "windows"},
    }
    body.update(overrides)
    return body


def test_ingest_requires_bearer_even_if_user_dependency_is_present(monkeypatch):
    client = make_client(monkeypatch, Database())
    response = client.post("/v1/environment/observations", json=observation())
    assert response.status_code == 401


def test_ingest_derives_owner_from_verified_identity_and_is_idempotent(monkeypatch):
    database = Database()
    client = make_client(monkeypatch, database)
    body = observation()
    first = client.post("/v1/environment/observations", json=body, headers={"Authorization": "Bearer valid"})
    second = client.post("/v1/environment/observations", json=body, headers={"Authorization": "Bearer valid"})
    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    assert len(database.rows) == 1
    assert database.rows[0]["user_id"] == "user-1"


def test_ingest_rejects_client_supplied_owner(monkeypatch):
    client = make_client(monkeypatch, Database())
    body = observation(user_id="another-user")
    response = client.post("/v1/environment/observations", json=body, headers={"Authorization": "Bearer valid"})
    assert response.status_code == 422


def test_mobile_token_must_be_bound_to_submitted_device(monkeypatch):
    client = make_client(monkeypatch, Database(), {"client": "jarvis-mobile", "device_id": "phone-1"})
    body = observation(device_id="phone-2", source_device_type="mobile")
    response = client.post("/v1/environment/observations", json=body, headers={"Authorization": "Bearer valid"})
    assert response.status_code == 403


def test_mobile_token_cannot_publish_desktop_observation(monkeypatch):
    client = make_client(monkeypatch, Database(), {"client": "jarvis-mobile", "device_id": "phone-1"})
    body = observation(device_id="phone-1")
    response = client.post("/v1/environment/observations", json=body, headers={"Authorization": "Bearer valid"})
    assert response.status_code == 403


def test_ingest_rejects_future_timestamp_and_sensitive_payload_keys(monkeypatch):
    client = make_client(monkeypatch, Database())
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    response = client.post(
        "/v1/environment/observations",
        json=observation(observed_at=future.isoformat()),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 422
    response = client.post(
        "/v1/environment/observations",
        json=observation(payload={"ssid": "private-network"}),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 422


def test_latest_returns_only_current_users_latest_records_with_freshness(monkeypatch):
    database = Database()
    now = datetime.now(timezone.utc)
    database.rows.extend([
        {
            "user_id": "user-1", "device_id": "desktop-main", "source_device_type": "desktop",
            "observation_type": "network_snapshot", "schema_version": 1,
            "observed_at": now.isoformat(), "received_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
            "payload": {"interfaces": []}, "request_id": str(uuid4()),
        },
        {
            "user_id": "user-1", "device_id": "phone-1", "source_device_type": "mobile",
            "observation_type": "network_snapshot", "schema_version": 1,
            "observed_at": now.isoformat(), "received_at": now.isoformat(),
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
            "payload": {"network_type": "wifi"}, "request_id": str(uuid4()),
        },
        {
            "user_id": "other-user", "device_id": "foreign", "source_device_type": "desktop",
            "observation_type": "network_snapshot", "schema_version": 1,
            "observed_at": now.isoformat(), "received_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
            "payload": {}, "request_id": str(uuid4()),
        },
    ])
    client = make_client(monkeypatch, database)
    response = client.get("/v1/environment/observations/latest", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200
    items = response.json()["observations"]
    assert {item["device_id"] for item in items} == {"desktop-main", "phone-1"}
    freshness = {item["device_id"]: item["freshness"] for item in items}
    assert freshness == {"desktop-main": "fresh", "phone-1": "stale"}


def test_storage_unavailable_fails_closed(monkeypatch):
    client = make_client(monkeypatch, None)
    response = client.post(
        "/v1/environment/observations", json=observation(),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 503



def test_api_server_registers_authenticated_observation_router():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    api = (root / "app" / "adapters" / "infrastructure" / "api_server.py").read_text(encoding="utf-8")
    assert "create_environment_observations_router" in api
    assert "app.include_router(create_environment_observations_router(get_current_user))" in api


def test_migration_restricts_table_to_server_role_and_enables_rls():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    migration = (
        root / "supabase" / "migrations" / "20261029120000_environment_observations.sql"
    ).read_text(encoding="utf-8")
    assert "enable row level security" in migration.lower()
    assert "revoke all on table public.jarvis_environment_observations from public, anon, authenticated, service_role" in migration.lower()
    assert "grant select, insert on table public.jarvis_environment_observations to service_role" in migration.lower()
    assert "unique (user_id, request_id)" in migration.lower()


def test_payload_size_is_bounded(monkeypatch):
    client = make_client(monkeypatch, Database())
    response = client.post(
        "/v1/environment/observations",
        json=observation(payload={"blob": "x" * (33 * 1024)}),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 422



def test_follow_up_migration_revokes_unneeded_server_privileges():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    migration = (
        root / "supabase" / "migrations" / "20261029110600_environment_observations_least_privilege.sql"
    ).read_text(encoding="utf-8").lower()
    assert "revoke all on table public.jarvis_environment_observations" in migration
    assert "from public, anon, authenticated, service_role" in migration
    assert "grant select, insert on table public.jarvis_environment_observations to service_role" in migration
