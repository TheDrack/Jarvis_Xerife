import asyncio

from app.adapters.infrastructure.soldier_bridge import SoldierBridgeManager


class FakeWebSocket:
    async def accept(self):
        pass

    async def send_json(self, _payload):
        pass


class TrackingSoldierBridgeManager(SoldierBridgeManager):
    def __init__(self):
        super().__init__()
        self.unregistered = []

    def _register_with_registry(self, _device_id, _device_type, _capabilities):
        pass

    def _unregister_from_registry(self, device_id):
        self.unregistered.append(device_id)


def test_stale_websocket_disconnect_does_not_remove_replacement_connection():
    manager = TrackingSoldierBridgeManager()
    device_id = "mobile:user-1:phone-1"
    old_socket = FakeWebSocket()
    new_socket = FakeWebSocket()

    asyncio.run(manager.connect(old_socket, device_id, "mobile", ["tts"]))
    asyncio.run(manager.connect(new_socket, device_id, "mobile", ["notifications"]))

    assert manager.disconnect(device_id, old_socket) is False
    assert manager.active_connections[device_id] is new_socket
    assert manager.get_device_type(device_id) == "mobile"
    assert manager.get_device_capabilities(device_id) == ["notifications"]
    assert manager.unregistered == []


def test_current_websocket_disconnect_removes_connection_and_capabilities():
    manager = TrackingSoldierBridgeManager()
    device_id = "mobile:user-1:phone-1"
    socket = FakeWebSocket()

    asyncio.run(manager.connect(socket, device_id, "mobile", ["tts"]))

    assert manager.disconnect(device_id, socket) is True
    assert device_id not in manager.active_connections
    assert manager.get_device_capabilities(device_id) == []
    assert manager.unregistered == [device_id]


def test_disconnect_without_socket_keeps_legacy_unconditional_behavior():
    manager = TrackingSoldierBridgeManager()
    device_id = "desktop-1"
    socket = FakeWebSocket()

    asyncio.run(manager.connect(socket, device_id, "desktop", ["pyautogui"]))

    assert manager.disconnect(device_id) is True
    assert device_id not in manager.active_connections
    assert manager.unregistered == [device_id]
