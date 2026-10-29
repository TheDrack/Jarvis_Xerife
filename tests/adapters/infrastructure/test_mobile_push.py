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
        self.event_types = []

    def is_configured(self):
        return self.configured

    def send_event(self, fcm_token, event_id, event_type="speak"):
        self.sent.append((fcm_token, event_id))
        self.event_types.append(event_type)


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
    def __init__(self, connected=None):
        self.connected = set(connected or [])
        self.sent_tasks = []

    def get_connected_devices(self):
        return list(self.connected)

    def is_device_connected(self, device_id):
        return device_id in self.connected

    def get_connected_soldiers(self):
        return []

    async def connect(self, *_args):
        raise AssertionError("Not used by this test")

    def disconnect(self, *_args):
        pass

    async def send_task(self, device_id, task, **_kwargs):
        self.sent_tasks.append((device_id, task))
        return {"success": True, "result": "notification_posted"}


def _setup(monkeypatch, database=None, sender=None, bridge_manager=None):
    auth = FakeAuth()
    db = database or FakeDatabase()
    push_sender = sender or FakeSender()
    manager = bridge_manager or FakeBridgeManager()
    monkeypatch.setattr(nexus, "resolve", lambda name: auth if name == "auth_adapter" else manager)
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


def test_return_activity_dispatch_requires_dedicated_machine_key(monkeypatch):
    client, _database, _sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_RETURN_ACTIVITY_KEY", "test-machine-key-that-is-at-least-32-characters-long")

    missing = client.post("/v1/mobile/push/return-activity", json={})
    invalid = client.post(
        "/v1/mobile/push/return-activity",
        json={},
        headers={"X-Jarvis-Return-Activity-Key": "wrong-key"},
    )
    assert missing.status_code == 401
    assert invalid.status_code == 401

    monkeypatch.setenv("JARVIS_RETURN_ACTIVITY_KEY", "short")
    short_key = client.post(
        "/v1/mobile/push/return-activity",
        json={},
        headers={"X-Jarvis-Return-Activity-Key": "short"},
    )
    assert short_key.status_code == 401


def test_return_activity_uses_fcm_when_mobile_websocket_is_offline(monkeypatch):
    client, database, sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_RETURN_ACTIVITY_KEY", "test-machine-key-that-is-at-least-32-characters-long")

    response = client.post(
        "/v1/mobile/push/return-activity",
        json={},
        headers={"X-Jarvis-Return-Activity-Key": "test-machine-key-that-is-at-least-32-characters-long"},
    )

    assert response.status_code == 200
    assert response.json()["transport"] == "fcm"
    assert response.json()["status"] == "queued"
    assert len(sender.sent) == 1
    event = database.tables[mobile_push.PUSH_EVENT_TABLE][0]
    assert event["payload"]["parameters"]["text"] == "Você voltou ao computador. Estou ativo e pronto para continuar."


def test_return_activity_fails_closed_if_multiple_phones_are_registered(monkeypatch):
    client, database, sender, _auth = _setup(monkeypatch)
    database.tables[mobile_push.PUSH_DEVICE_TABLE].append({
        "user_id": "user-99",
        "device_id": "phone-2",
        "fcm_token": "g" * 64,
        "revoked_at": None,
    })
    monkeypatch.setenv("JARVIS_RETURN_ACTIVITY_KEY", "test-machine-key-that-is-at-least-32-characters-long")

    response = client.post(
        "/v1/mobile/push/return-activity",
        json={},
        headers={"X-Jarvis-Return-Activity-Key": "test-machine-key-that-is-at-least-32-characters-long"},
    )

    assert response.status_code == 409
    assert sender.sent == []
    assert database.tables[mobile_push.PUSH_EVENT_TABLE] == []


def test_return_activity_prefers_websocket_when_phone_is_connected(monkeypatch):
    client, database, sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_RETURN_ACTIVITY_KEY", "test-machine-key-that-is-at-least-32-characters-long")
    calls = []

    class ConnectedBridge:
        def is_device_connected(self, device_id):
            return device_id == "mobile:user-42:phone-1"

        async def send_task(self, device_id, task, api_key=None):
            calls.append((device_id, task, api_key))
            return {"success": True, "result": "speech_completed"}

    auth = FakeAuth()
    manager = ConnectedBridge()
    monkeypatch.setattr(
        nexus,
        "resolve",
        lambda name: auth if name == "auth_adapter" else manager,
    )

    response = client.post(
        "/v1/mobile/push/return-activity",
        json={},
        headers={"X-Jarvis-Return-Activity-Key": "test-machine-key-that-is-at-least-32-characters-long"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "delivered", "transport": "websocket"}
    assert calls[0][0] == "mobile:user-42:phone-1"
    assert calls[0][1]["action"] == "speak"
    assert calls[0][2] is None
    assert sender.sent == []
    assert database.tables[mobile_push.PUSH_EVENT_TABLE] == []



def test_offline_notification_event_persists_text_and_sends_only_opaque_id(monkeypatch):
    _client, database, sender, _auth = _setup(monkeypatch)
    result = mobile_push.dispatch_mobile_event(
        "user-42", "phone-1", "Estoque atualizado", mode="notification", title="Jarvis"
    )

    assert result["status"] == "queued"
    event = database.tables[mobile_push.PUSH_EVENT_TABLE][0]
    assert event["event_type"] == "notification"
    assert event["payload"] == {
        "action": "notification",
        "parameters": {"title": "Jarvis", "text": "Estoque atualizado"},
    }
    assert sender.sent == [("f" * 64, result["event_id"])]
    assert sender.event_types == ["notification"]


def test_agent_notification_fails_closed_when_server_key_is_missing(monkeypatch):
    client, _database, _sender, _auth = _setup(monkeypatch)
    monkeypatch.delenv("JARVIS_MOBILE_NOTIFY_KEY", raising=False)

    response = client.post(
        "/v1/mobile/push/notify",
        json={"device_id": "phone-1", "text": "Teste"},
        headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64},
    )

    assert response.status_code == 503


def test_agent_notification_rejects_wrong_service_key(monkeypatch):
    client, _database, _sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "a" * 64)

    response = client.post(
        "/v1/mobile/push/notify",
        json={"device_id": "phone-1", "text": "Teste"},
        headers={"X-Jarvis-Mobile-Notify-Key": "b" * 64},
    )

    assert response.status_code == 401


def test_agent_notification_uses_registered_device_and_returns_queued_ack_id(monkeypatch):
    client, database, sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)

    response = client.post(
        "/v1/mobile/push/notify",
        json={
            "device_id": "phone-1",
            "user_id": "user-42",
            "title": "Jarvis",
            "text": "Teste de notificação",
            "mode": "notification",
        },
        headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["transport"] == "fcm"
    event = database.tables[mobile_push.PUSH_EVENT_TABLE][0]
    assert event["event_id"] == response.json()["event_id"]
    assert event["event_type"] == "notification"
    assert sender.event_types == ["notification"]


def test_agent_device_listing_never_exposes_fcm_tokens(monkeypatch):
    client, _database, _sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)

    response = client.get(
        "/v1/mobile/push/agent/devices",
        headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64},
    )

    assert response.status_code == 200
    device = response.json()["devices"][0]
    assert device["device_id"] == "phone-1"
    assert device["push_registered"] is True
    assert "fcm_token" not in device



def test_agent_notification_uses_websocket_and_waits_for_task_ack(monkeypatch):
    manager = FakeBridgeManager(connected={"mobile:user-42:phone-1"})
    client, database, sender, _auth = _setup(monkeypatch, bridge_manager=manager)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)

    response = client.post(
        "/v1/mobile/push/notify",
        json={
            "device_id": "phone-1",
            "user_id": "user-42",
            "title": "Jarvis",
            "text": "Teste pelo WebSocket",
            "mode": "notification",
        },
        headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "delivered"
    assert response.json()["transport"] == "websocket"
    assert manager.sent_tasks == [(
        "mobile:user-42:phone-1",
        {"action": "notification", "parameters": {"title": "Jarvis", "text": "Teste pelo WebSocket"}},
    )]
    assert database.tables[mobile_push.PUSH_EVENT_TABLE] == []
    assert sender.sent == []



def test_agent_event_status_reports_acknowledged_without_exposing_payload(monkeypatch):
    client, database, _sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)
    event_id = "d2a6f6d2-5312-4b58-9c3a-90a1f8e27e25"
    database.tables[mobile_push.PUSH_EVENT_TABLE].append({
        "event_id": event_id,
        "user_id": "user-42",
        "device_id": "phone-1",
        "event_type": "notification",
        "payload": {},
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
    })

    response = client.get(
        f"/v1/mobile/push/agent/events/{event_id}",
        headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"
    assert "payload" not in response.json()


def test_agent_event_status_reports_expired_unacknowledged_event(monkeypatch):
    client, database, _sender, _auth = _setup(monkeypatch)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)
    event_id = "a5f3a8a8-1ed9-4a2b-a84a-cb3df5bb0e31"
    database.tables[mobile_push.PUSH_EVENT_TABLE].append({
        "event_id": event_id,
        "user_id": "user-42",
        "device_id": "phone-1",
        "event_type": "notification",
        "payload": {"action": "notification", "parameters": {"text": "private"}},
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "acknowledged_at": None,
    })

    response = client.get(
        f"/v1/mobile/push/agent/events/{event_id}",
        headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "expired"
    assert "payload" not in response.json()
