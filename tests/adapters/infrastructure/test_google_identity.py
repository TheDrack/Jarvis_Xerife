from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers import google_identity
from app.core.nexus import nexus


class Response:
    def __init__(self, data=None):
        self.data = data or []


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.op, self.payload, self.filters = None, None, {}

    def select(self, _):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, _):
        return self

    def execute(self):
        if self.op == "insert":
            if self.table == google_identity.IDENTITY_TABLE:
                if any(x["provider_subject"] == self.payload["provider_subject"] for x in self.db.identities):
                    raise ValueError("duplicate")
                self.db.identities.append(self.payload)
            elif self.table == google_identity.SESSION_TABLE:
                self.db.sessions.append(self.payload)
            else:
                raise AssertionError(self.table)
            return Response([self.payload])
        rows = self.db.rows.get(self.table, [])
        for key, value in self.filters.items():
            rows = [row for row in rows if row.get(key) == value]
        return Response(rows[:2])


class Database:
    def __init__(self):
        self.identities, self.sessions = [], []
        self.rows = {
            "user": [{"id": "user-7", "email": "person@example.com", "username": "person@example.com",
                      "full_name": "Existing User", "disabled": False}],
            "users": [],
        }

    def table(self, name):
        return Query(self, name)


class Auth:
    def create_access_token(self, data, expires_delta=None):
        assert expires_delta == 15
        self.claims = data
        return "signed-access-token"


def client(monkeypatch, db=None, identity=None):
    db = db or Database()
    monkeypatch.setattr(google_identity, "_verify_google_identity", lambda _: identity or {
        "subject": "google-sub-1", "email": "person@example.com", "full_name": "Google Name"
    })
    monkeypatch.setattr(google_identity, "get_supabase_admin_client", lambda: db)
    auth = Auth()
    monkeypatch.setattr(nexus, "resolve", lambda name: auth if name == "auth_adapter" else None)
    app = FastAPI()
    app.include_router(google_identity.create_google_identity_router())
    return TestClient(app), db, auth


def test_google_login_links_verified_identity_to_existing_jarvis_account(monkeypatch):
    test_client, db, auth = client(monkeypatch)
    response = test_client.post("/v1/mobile/session/google", json={"id_token": "valid-id-token-long-enough", "device_id": "android-1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "signed-access-token"
    assert db.identities[0]["user_id"] == "user-7"
    assert db.identities[0]["provider_subject"] == "google-sub-1"
    assert db.sessions[0]["user_id"] == "user-7"
    assert db.sessions[0]["token_hash"] not in payload["refresh_token"]
    assert auth.claims["auth_provider"] == "google"
    assert auth.claims["user_id"] == "user-7"


def test_google_login_reuses_existing_identity_without_duplicate_link(monkeypatch):
    db = Database()
    db.identities.append({"provider": "google", "provider_subject": "google-sub-1", "user_id": "user-7",
                          "email": "person@example.com", "full_name": "Existing User"})
    test_client, db, _ = client(monkeypatch, db)
    response = test_client.post("/v1/mobile/session/google", json={"id_token": "valid-id-token-long-enough", "device_id": "android-1"})
    assert response.status_code == 200
    assert len(db.identities) == 1


def test_google_login_refuses_to_create_or_link_unknown_account(monkeypatch):
    test_client, db, _ = client(monkeypatch, identity={
        "subject": "new-google-sub", "email": "unknown@example.com", "full_name": "Unknown"
    })
    response = test_client.post("/v1/mobile/session/google", json={"id_token": "valid-id-token-long-enough", "device_id": "android-1"})
    assert response.status_code == 403
    assert db.identities == []
    assert db.sessions == []


def test_google_login_refuses_without_admin_storage(monkeypatch):
    test_client, _, _ = client(monkeypatch, None)
    monkeypatch.setattr(google_identity, "get_supabase_admin_client", lambda: None)
    response = test_client.post("/v1/mobile/session/google", json={"id_token": "valid-id-token-long-enough", "device_id": "android-1"})
    assert response.status_code == 503



def test_google_login_rejects_mapping_to_deleted_jarvis_account(monkeypatch):
    db = Database()
    db.identities.append({"provider": "google", "provider_subject": "google-sub-1", "user_id": "deleted-user",
                          "email": "person@example.com", "full_name": "Old User"})
    db.rows = {"user": [], "users": []}
    test_client, db, _ = client(monkeypatch, db)
    response = test_client.post("/v1/mobile/session/google", json={"id_token": "valid-id-token-long-enough", "device_id": "android-1"})
    assert response.status_code == 403
    assert db.sessions == []
