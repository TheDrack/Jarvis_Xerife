from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers import bridge, mobile_push
from app.core.nexus import nexus


class FakeResponse:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, database, table_name):
        self.database = database
        self.table_name = table_name
        self.operation = None
        self.payload = None
        self.filters = {}
        self.greater_than = {}
        self.less_than = {}

    def select(self, _columns):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation, self.payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self.operation, self.payload = "upsert", payload
        return self

    def update(self, payload):
        self.operation, self.payload = "update", payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def is_(self, key, value):
        self.filters[key] = None if value == "null" else value
        return self

    def gt(self, key, value):
        self.greater_than[key] = value
        return self

    def lt(self, key, value):
        self.less_than[key] = value
        return self

    def limit(self, _limit):
        return self

    def execute(self):
        rows = self.database.tables.setdefault(self.table_name, [])
        if self.operation == "insert":
            rows.append(dict(self.payload))
            return FakeResponse([self.payload])
        if self.operation == "upsert":
            for row in rows:
                if row.get("user_id") == self.payload.get("user_id") and row.get("device_id") == self.payload.get("device_id"):
                    row.update(self.payload)
                    return FakeResponse([row])
            rows.append(dict(self.payload))
            return FakeResponse([self.payload])
        matching = [
            row for row in rows
            if all(row.get(key) == value for key, value in self.filters.items())
            and all(str(row.get(key, "")) > value for key, value in self.greater_than.items())
            and all(str(row.get(key, "")) < value for key, value in self.less_than.items())
        ]
        if self.operation == "delete":
            rows[:] = [row for row in rows if row not in matching]
            return FakeResponse(matching)
        if self.operation == "select":
            return FakeResponse([dict(row) for row in matching])
        if self.operation == "update":
            for row in matching:
                row.update(self.payload)
            return FakeResponse(matching)
        raise AssertionError("Unexpected fake database operation")


class FakeDatabase:
    def __init__(self):
        self.tables = {
            mobile_push.PUSH_DEVICE_TABLE: [{
                "user_id": "user-42",
                "device_id": "phone-1",
                "fcm_token": "f" * 64,
                "revoked_at": None,
            }],
            mobile_push.PUSH_EVENT_TABLE: [],
        }

    def table(self, name):
        return FakeQuery(self, name)


class FakeSender:
    def __init__(self, configured=True):
        self.configured = configured
        self.sent = []

    def is_configured(self):
        return self.configured

    def send_event(self, fcm_token, event_id):
        self.sent.append((fcm_token, event_id))


class FakeAuth:
    def verify_token(self, token):
        if token == "valid":
            return {
                "sub": "felipe",
                "user_id": "user-42",
                "device_id": "phone-1",
                "client": "jarvis-mobile",
            }
        if token == "other":
            return {
                "sub": "other-user",
                "user_id": "user-99",
                "device_id": "phone-2",
                "client": "jarvis-mobile",
            }
        return None


class FakeBridgeManager:
    def is_device_connected(self, _device_id):
        return False

    def get_connected_soldiers(self):
        return []

    async def connect(self, *_args):
        raise AssertionError("Not used by this test")

    def disconnect(self, *_args):
        pass

    async def send_task(self, *_args, **_kwargs):
        raise AssertionError("Offline fallback should be used")


def _setup(monkeypatch, database=None, sender=None):
    auth = FakeAuth()
    db = database or FakeDatabase()
    push_sender = sender or FakeSender()
    monkeypatch.setattr(nexus, "resolve", lambda name: auth if name == "auth_adapter" else FakeBridgeManager())
    monkeypatch.setattr(mobile_push, "get_supabase_admin_client", lambda: db)
    monkeypatch.setattr(mobile_push, "_push_sender", push_sender)
    app = FastAPI()
    app.include_router(mobile_push.create_mobile_push_router())
    return TestClient(app), db, push_sender, auth


def test_push_registration_requires_matching_native_device_session(monkeypatch):
    client, database, _sender, _auth = _setup(monkeypatch)
    response = client.post(
        "/v1/mobile/push/register",
        json={"device_id": "phone-1", "fcm_token": "new-token-" + "x" * 48},
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 204
    row = database.tables[mobile_push.PUSH_DEVICE_TABLE][0]
    assert row["user_id"] == "user-42"
    assert row["device_id"] == "phone-1"
    assert row["fcm_token"] == "new-token-" + "x" * 48
    assert row["revoked_at"] is None


def test_push_registration_rejects_a_different_device_id(monkeypatch):
    client, _database, _sender, _auth = _setup(monkeypatch)
    response = client.post(
        "/v1/mobile/push/register",
        json={"device_id": "phone-2", "fcm_token": "x" * 64},
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 403


def test_offline_speech_event_persists_payload_but_sends_only_opaque_id(monkeypatch):
    _client, database, sender, _auth = _setup(monkeypatch)
    result = mobile_push.dispatch_mobile_speak("user-42", "phone-1", "Jarvis está de volta")

    assert result["status"] == "queued"
    event_id = result["event_id"]
    event = database.tables[mobile_push.PUSH_EVENT_TABLE][0]
    assert event["event_id"] == event_id
    assert event["payload"]["parameters"]["text"] == "Jarvis está de volta"
    assert sender.sent == [("f" * 64, event_id)]


def test_fcm_dispatch_fails_closed_without_firebase_credentials(monkeypatch):
    _client, _database, sender, _auth = _setup(monkeypatch, sender=FakeSender(configured=False))
    try:
        mobile_push.dispatch_mobile_speak("user-42", "phone-1", "Jarvis está de volta")
        raise AssertionError("Push dispatch unexpectedly worked without Firebase configuration")
    except Exception as exc:
        assert type(exc).__name__ == "FirebasePushNotConfigured"


def test_push_event_fetch_is_scoped_to_authenticated_user_and_device(monkeypatch):
    client, database, _sender, _auth = _setup(monkeypatch)
    event_id = "f4e2d6a1-7c2e-4c87-9c30-83e57d90cbf4"
    database.tables[mobile_push.PUSH_EVENT_TABLE].append({
        "event_id": event_id,
        "user_id": "user-42",
        "device_id": "phone-1",
        "event_type": "speak",
        "payload": {"action": "speak", "parameters": {"text": "Jarvis está de volta"}},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(),
        "acknowledged_at": None,
    })

    response = client.get(
        f"/v1/mobile/push/events/{event_id}",
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 200
    assert response.json()["payload"]["parameters"]["text"] == "Jarvis está de volta"


def test_push_event_acknowledgement_prevents_replay(monkeypatch):
    client, database, _sender, _auth = _setup(monkeypatch)
    event_id = "f4e2d6a1-7c2e-4c87-9c30-83e57d90cbf4"
    database.tables[mobile_push.PUSH_EVENT_TABLE].append({
        "event_id": event_id,
        "user_id": "user-42",
        "device_id": "phone-1",
        "event_type": "speak",
        "payload": {"action": "speak", "parameters": {"text": "Jarvis está de volta"}},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(),
        "acknowledged_at": None,
    })

    ack = client.post(
        f"/v1/mobile/push/events/{event_id}/ack",
        headers={"Authorization": "Bearer valid"},
    )
    assert ack.status_code == 204
    fetched = client.get(
        f"/v1/mobile/push/events/{event_id}",
        headers={"Authorization": "Bearer valid"},
    )
    assert fetched.status_code == 404


def test_offline_bridge_routes_only_speak_tasks_to_push(monkeypatch):
    auth = FakeAuth()
    calls = []
    monkeypatch.setattr(nexus, "resolve", lambda name: auth if name == "auth_adapter" else FakeBridgeManager())
    monkeypatch.setattr(
        bridge,
        "dispatch_mobile_speak",
        lambda user_id, device_id, text: calls.append((user_id, device_id, text)) or {"status": "queued"},
    )
    app = FastAPI()
    app.include_router(bridge.create_bridge_router())
    client = TestClient(app)

    response = client.post(
        "/v1/local-bridge/send-task?device_id=mobile%3Auser-42%3Aphone-1",
        json={"action": "speak", "parameters": {"text": "Jarvis está de volta"}},
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 200
    assert calls == [("user-42", "phone-1", "Jarvis está de volta")]

    unsupported = client.post(
        "/v1/local-bridge/send-task?device_id=mobile%3Auser-42%3Aphone-1",
        json={"action": "shell", "parameters": {"command": "whoami"}},
        headers={"Authorization": "Bearer valid"},
    )
    assert unsupported.status_code == 422
    assert len(calls) == 1


def test_fcm_token_reassignment_revokes_previous_active_owner(monkeypatch):
    client, database, _sender, _auth = _setup(monkeypatch)
    response = client.post(
        "/v1/mobile/push/register",
        json={"device_id": "phone-2", "fcm_token": "f" * 64},
        headers={"Authorization": "Bearer other"},
    )
    assert response.status_code == 204
    active = [
        row for row in database.tables[mobile_push.PUSH_DEVICE_TABLE]
        if row["fcm_token"] == "f" * 64 and row["revoked_at"] is None
    ]
    assert active == [{
        "user_id": "user-99",
        "device_id": "phone-2",
        "fcm_token": "f" * 64,
        "updated_at": active[0]["updated_at"],
        "revoked_at": None,
    }]
