from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers import mobile_push
from app.core.nexus import nexus


class FakeResponse:
    def __init__(self, data=None): self.data = data


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.operation, self.payload = None, None
        self.filters, self.greater, self.less = {}, {}, {}
    def select(self, _columns): self.operation = "select"; return self
    def insert(self, payload): self.operation, self.payload = "insert", payload; return self
    def upsert(self, payload, on_conflict=None): self.operation, self.payload = "upsert", payload; return self
    def update(self, payload): self.operation, self.payload = "update", payload; return self
    def delete(self): self.operation = "delete"; return self
    def eq(self, key, value): self.filters[key] = value; return self
    def is_(self, key, value): self.filters[key] = None if value == "null" else value; return self
    def gt(self, key, value): self.greater[key] = value; return self
    def lt(self, key, value): self.less[key] = value; return self
    def limit(self, _limit): return self
    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        matches = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())
                   and all(str(r.get(k, "")) > v for k, v in self.greater.items())
                   and all(str(r.get(k, "")) < v for k, v in self.less.items())]
        if self.operation == "insert":
            rows.append(dict(self.payload)); return FakeResponse([self.payload])
        if self.operation == "upsert":
            for row in rows:
                if row.get("user_id") == self.payload.get("user_id") and row.get("device_id") == self.payload.get("device_id"):
                    row.update(self.payload); return FakeResponse([row])
            rows.append(dict(self.payload)); return FakeResponse([self.payload])
        if self.operation == "update":
            for row in matches: row.update(self.payload)
            return FakeResponse(matches)
        if self.operation == "delete":
            rows[:] = [r for r in rows if r not in matches]; return FakeResponse(matches)
        if self.operation == "select": return FakeResponse([dict(r) for r in matches])
        raise AssertionError(self.operation)


class FakeDatabase:
    def __init__(self): self.tables = {mobile_push.DEVICE_TABLE: [], mobile_push.EVENT_TABLE: []}
    def table(self, name): return FakeQuery(self, name)


class FakeAuth:
    def verify_token(self, token):
        if token == "valid":
            return {"sub": "user-42", "user_id": "user-42", "device_id": "phone-1", "client": "jarvis-mobile"}
        return None


class FakeBridge:
    def __init__(self, connected=None): self.connected, self.sent = set(connected or []), []
    def get_connected_devices(self): return list(self.connected)
    def is_device_connected(self, device_id): return device_id in self.connected
    async def send_task(self, device_id, task, api_key=None):
        self.sent.append((device_id, task, api_key))
        return {"success": True, "result": "notification_posted"}


def setup(monkeypatch, connected=None):
    db, manager = FakeDatabase(), FakeBridge(connected)
    monkeypatch.setattr(mobile_push, "get_supabase_admin_client", lambda: db)
    monkeypatch.setattr(nexus, "resolve", lambda name: FakeAuth() if name == "auth_adapter" else manager)
    app = FastAPI(); app.include_router(mobile_push.create_mobile_push_router())
    return TestClient(app), db, manager


def register(client):
    return client.post("/v1/mobile/push/register", json={"device_id": "phone-1"}, headers={"Authorization": "Bearer valid"})


def test_mobile_device_registration_requires_native_session(monkeypatch):
    client, db, _ = setup(monkeypatch)
    response = register(client)
    assert response.status_code == 204
    assert db.tables[mobile_push.DEVICE_TABLE][0]["device_id"] == "phone-1"
    assert "fcm_token" not in db.tables[mobile_push.DEVICE_TABLE][0]


def test_agent_notification_queues_for_offline_registered_device(monkeypatch):
    client, db, _ = setup(monkeypatch)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)
    assert register(client).status_code == 204
    response = client.post("/v1/mobile/push/notify", json={"device_id": "phone-1", "user_id": "user-42", "text": "Teste", "mode": "notification"}, headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued" and payload["transport"] == "queue"
    assert db.tables[mobile_push.EVENT_TABLE][0]["payload"]["parameters"]["text"] == "Teste"


def test_pending_events_are_scoped_and_acknowledged(monkeypatch):
    client, db, _ = setup(monkeypatch)
    assert register(client).status_code == 204
    event_id = "d2a6f6d2-5312-4b58-9c3a-90a1f8e27e25"
    db.tables[mobile_push.EVENT_TABLE].append({
        "event_id": event_id, "user_id": "user-42", "device_id": "phone-1",
        "event_type": "notification", "payload": {"action": "notification", "parameters": {"text": "Private", "title": "Jarvis"}},
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(), "acknowledged_at": None,
    })
    response = client.get("/v1/mobile/push/events/pending", headers={"Authorization": "Bearer valid"})
    assert response.status_code == 200 and response.json()["count"] == 1
    ack = client.post(f"/v1/mobile/push/events/{event_id}/ack", headers={"Authorization": "Bearer valid"})
    assert ack.status_code == 204
    assert db.tables[mobile_push.EVENT_TABLE][0]["payload"] == {}


def test_agent_notification_rejects_missing_or_wrong_credential(monkeypatch):
    client, _, _ = setup(monkeypatch)
    response = client.post("/v1/mobile/push/notify", json={"text": "x"}, headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64})
    assert response.status_code == 503
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "a" * 64)
    response = client.post("/v1/mobile/push/notify", json={"text": "x"}, headers={"X-Jarvis-Mobile-Notify-Key": "b" * 64})
    assert response.status_code == 401


def test_connected_device_delivery_uses_native_websocket(monkeypatch):
    client, db, manager = setup(monkeypatch, {"mobile:user-42:phone-1"})
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)
    response = client.post("/v1/mobile/push/notify", json={"device_id": "phone-1", "user_id": "user-42", "text": "Teste", "mode": "notification"}, headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64})
    assert response.status_code == 200 and response.json()["transport"] == "websocket"
    assert manager.sent[0][2] is None
    assert db.tables[mobile_push.EVENT_TABLE] == []


def test_agent_event_status_reports_expired(monkeypatch):
    client, db, _ = setup(monkeypatch)
    monkeypatch.setenv("JARVIS_MOBILE_NOTIFY_KEY", "k" * 64)
    event_id = "a5f3a8a8-1ed9-4a2b-a84a-cb3df5bb0e31"
    db.tables[mobile_push.EVENT_TABLE].append({"event_id": event_id, "user_id": "user-42", "device_id": "phone-1", "event_type": "notification", "payload": {}, "expires_at": (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(), "acknowledged_at": None})
    response = client.get(f"/v1/mobile/push/agent/events/{event_id}", headers={"X-Jarvis-Mobile-Notify-Key": "k" * 64})
    assert response.status_code == 200 and response.json()["status"] == "expired"
