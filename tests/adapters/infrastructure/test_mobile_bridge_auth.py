from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.adapters.infrastructure.routers.bridge import create_bridge_router
from app.core.nexus import nexus


class FakeBridgeManager:
    def __init__(self):
        self.connected = []
        self.disconnected = []
        self.messages = []
        self.sent_tasks = []

    async def connect(self, websocket, device_id, device_type, capabilities):
        self.connected.append((device_id, device_type, capabilities))
        await websocket.accept()

    async def handle_message(self, device_id, data):
        self.messages.append((device_id, data))

    def disconnect(self, device_id):
        self.disconnected.append(device_id)

    def is_device_connected(self, device_id):
        return True

    def get_connected_soldiers(self):
        return []

    async def send_task(self, device_id, task, api_key):
        self.sent_tasks.append((device_id, task, api_key))
        return {"ok": True}


class FakeAuthAdapter:
    def verify_token(self, token):
        if token == "valid":
            return {"sub": "felipe", "user_id": "user-123"}
        return None


def _client(monkeypatch, manager):
    auth = FakeAuthAdapter()

    def resolve(name):
        if name == "soldier_bridge":
            return manager
        if name == "auth_adapter":
            return auth
        raise KeyError(name)

    monkeypatch.setattr(nexus, "resolve", resolve)
    app = FastAPI()
    app.include_router(create_bridge_router())
    return TestClient(app)


def test_mobile_websocket_rejects_missing_bearer_token(monkeypatch):
    manager = FakeBridgeManager()
    client = _client(monkeypatch, manager)

    try:
        with client.websocket_connect(
            "/v1/local-bridge?device_id=phone-1&device_type=mobile"
        ):
            raise AssertionError("Unauthenticated mobile connection unexpectedly opened")
    except WebSocketDisconnect:
        pass

    assert manager.connected == []


def test_mobile_websocket_rejects_invalid_bearer_token(monkeypatch):
    manager = FakeBridgeManager()
    client = _client(monkeypatch, manager)

    try:
        with client.websocket_connect(
            "/v1/local-bridge?device_id=phone-1&device_type=mobile",
            headers={"Authorization": "Bearer invalid"},
        ):
            raise AssertionError("Invalid token unexpectedly connected")
    except WebSocketDisconnect:
        pass

    assert manager.connected == []


def test_mobile_websocket_namespaces_device_by_authenticated_user(monkeypatch):
    manager = FakeBridgeManager()
    client = _client(monkeypatch, manager)

    with client.websocket_connect(
        "/v1/local-bridge?device_id=phone-1&device_type=mobile&capabilities=tts,notifications",
        headers={"Authorization": "Bearer valid"},
    ) as websocket:
        websocket.send_json({"type": "ping"})
        # Keep the session open long enough for the receive loop to handle a message.
        websocket.send_json({"type": "disconnect-test"})

    assert manager.connected == [
        ("mobile:user-123:phone-1", "mobile", ["tts", "notifications"])
    ]
    assert manager.disconnected == ["mobile:user-123:phone-1"]
    assert all(device_id == "mobile:user-123:phone-1" for device_id, _ in manager.messages)



def test_bridge_task_dispatch_rejects_missing_authentication(monkeypatch):
    manager = FakeBridgeManager()
    client = _client(monkeypatch, manager)
    monkeypatch.setenv("API_KEY_LOCAL", "server-side-test-key")

    response = client.post(
        "/v1/local-bridge/send-task?device_id=desktop-1",
        json={"action": "status"},
    )

    assert response.status_code == 401
    assert manager.sent_tasks == []


def test_bridge_task_dispatch_requires_auth_and_passes_server_key(monkeypatch):
    manager = FakeBridgeManager()
    client = _client(monkeypatch, manager)
    monkeypatch.setenv("API_KEY_LOCAL", "server-side-test-key")

    response = client.post(
        "/v1/local-bridge/send-task?device_id=desktop-1",
        json={"action": "status"},
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert manager.sent_tasks == [
        ("desktop-1", {"action": "status"}, "server-side-test-key")
    ]


def test_bridge_device_listing_requires_authentication(monkeypatch):
    manager = FakeBridgeManager()
    client = _client(monkeypatch, manager)

    response = client.get("/v1/local-bridge/devices")

    assert response.status_code == 401
