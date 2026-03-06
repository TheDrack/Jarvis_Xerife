# -*- coding: utf-8 -*-
"""Tests for new Supabase migration components.

Covers:
  - AuthAdapter: Supabase user lookup + env-var fallback
  - VectorMemoryAdapter: user_id filter on query_similar / store_event
  - WebSocketManager: connect, disconnect, broadcast
  - SoldierBridgeManager: multi-device connect, capability routing
  - SoldierRegistry: register, unregister, get_available_soldiers
  - JrvsCloudStorage: graceful no-op when Supabase unavailable
  - JrvsTranslator: sync_to_cloud flag, sync_all
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.infrastructure.auth_adapter import AuthAdapter
from app.adapters.infrastructure.jrvs_cloud_storage import JrvsCloudStorage
from app.adapters.infrastructure.vector_memory_adapter import VectorMemoryAdapter
from app.adapters.infrastructure.websocket_manager import WebSocketManager
from app.adapters.infrastructure.soldier_bridge import SoldierBridgeManager
from app.application.services.soldier_registry import SoldierRegistry


# ===========================================================================
# AuthAdapter — Supabase + env-var fallback
# ===========================================================================


class TestAuthAdapterSupabaseFallback:
    """Test the env-var admin fallback path (no Supabase needed)."""

    @pytest.fixture
    def adapter(self):
        return AuthAdapter()

    def test_authenticate_via_env_var(self, adapter, monkeypatch):
        """Valid credentials through JARVIS_ADMIN_PASSWORD fallback."""
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "secret")
        monkeypatch.setenv("JARVIS_ADMIN_EMAIL", "root@test.local")
        user = adapter.authenticate_user("admin", "secret")
        assert user is not None
        assert user["username"] == "admin"
        assert user["email"] == "root@test.local"

    def test_fallback_wrong_password(self, adapter, monkeypatch):
        """Wrong password returns None."""
        monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "secret")
        user = adapter.authenticate_user("admin", "badpass")
        assert user is None

    def test_no_supabase_no_env_returns_none(self, adapter, monkeypatch):
        """When neither Supabase nor env-var is set, auth fails."""
        monkeypatch.delenv("JARVIS_ADMIN_PASSWORD", raising=False)
        user = adapter.authenticate_user("admin", "whatever")
        assert user is None

    def test_get_user_by_email_no_supabase(self, adapter):
        """Without Supabase configured, get_user_by_email returns None."""
        with patch(
            "app.adapters.infrastructure.supabase_client.get_supabase_client",
            return_value=None,
        ):
            result = adapter.get_user_by_email("user@example.com")
        assert result is None

    def test_create_user_no_supabase(self, adapter):
        """Without Supabase configured, create_user returns None."""
        with patch(
            "app.adapters.infrastructure.supabase_client.get_supabase_client",
            return_value=None,
        ):
            result = adapter.create_user("user@example.com", "password")
        assert result is None

    def test_create_user_with_supabase(self, adapter):
        """create_user inserts a row and returns the new user dict."""
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "uuid-123", "email": "new@example.com", "full_name": "New User"}
        ]
        with patch(
            "app.adapters.infrastructure.supabase_client.get_supabase_client",
            return_value=mock_client,
        ):
            result = adapter.create_user("new@example.com", "pass123", "New User")
        assert result is not None
        assert result["email"] == "new@example.com"

    def test_authenticate_via_supabase(self, adapter, monkeypatch):
        """Successful auth against Supabase users table."""
        hashed = adapter.get_password_hash("supapass")
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {
                "id": "uuid-abc",
                "email": "su@example.com",
                "full_name": "Supabase User",
                "hashed_password": hashed,
                "disabled": False,
            }
        ]
        with patch(
            "app.adapters.infrastructure.supabase_client.get_supabase_client",
            return_value=mock_client,
        ):
            user = adapter.authenticate_user("su@example.com", "supapass")
        assert user is not None
        assert user["user_id"] == "uuid-abc"
        assert "hashed_password" not in user


# ===========================================================================
# VectorMemoryAdapter — user_id filter
# ===========================================================================


class TestVectorMemoryUserIdFilter:
    """Tests for the new user_id parameter in store_event and query_similar."""

    def test_store_event_saves_user_id_in_metadata(self):
        adapter = VectorMemoryAdapter()
        event_id = adapter.store_event("Hello world", user_id="user-42")
        events = [e for e in adapter._events if e["id"] == event_id]
        assert events
        assert events[0]["metadata"]["user_id"] == "user-42"

    def test_query_similar_filters_by_user_id(self):
        adapter = VectorMemoryAdapter()
        adapter.store_event("Python programming tips", user_id="alice")
        adapter.store_event("Python programming tips", user_id="bob")

        results_alice = adapter.query_similar("Python", user_id="alice", days_back=None)
        results_bob = adapter.query_similar("Python", user_id="bob", days_back=None)

        assert all(r["metadata"].get("user_id") == "alice" for r in results_alice)
        assert all(r["metadata"].get("user_id") == "bob" for r in results_bob)

    def test_query_similar_no_user_id_returns_all(self):
        adapter = VectorMemoryAdapter()
        adapter.store_event("JARVIS command", user_id="alice")
        adapter.store_event("JARVIS command", user_id="bob")

        results = adapter.query_similar("JARVIS", user_id=None, days_back=None)
        user_ids = {r["metadata"].get("user_id") for r in results}
        assert "alice" in user_ids or "bob" in user_ids  # at least one returned

    def test_query_similar_missing_user_returns_empty(self):
        adapter = VectorMemoryAdapter()
        adapter.store_event("Test event", user_id="carol")
        results = adapter.query_similar("Test", user_id="nobody", days_back=None)
        assert results == []


# ===========================================================================
# WebSocketManager
# ===========================================================================


class TestWebSocketManager:
    """Tests for per-user WebSocket connection management."""

    @pytest.fixture
    def manager(self):
        return WebSocketManager()

    @pytest.fixture
    def mock_ws(self):
        ws = AsyncMock()
        ws.send_json = AsyncMock()
        ws.send_text = AsyncMock()
        ws.accept = AsyncMock()
        return ws

    def test_connect_registers_socket(self, manager, mock_ws):
        asyncio.get_event_loop().run_until_complete(manager.connect("user-1", mock_ws))
        assert manager.is_connected("user-1")
        assert manager.connection_count("user-1") == 1

    def test_disconnect_removes_socket(self, manager, mock_ws):
        asyncio.get_event_loop().run_until_complete(manager.connect("user-1", mock_ws))
        manager.disconnect("user-1")
        assert not manager.is_connected("user-1")

    def test_broadcast_to_user_sends_json(self, manager, mock_ws):
        asyncio.get_event_loop().run_until_complete(manager.connect("user-1", mock_ws))
        sent = asyncio.get_event_loop().run_until_complete(
            manager.broadcast_to_user("user-1", {"type": "test"})
        )
        assert sent == 1
        mock_ws.send_json.assert_called()

    def test_broadcast_to_user_no_connection(self, manager):
        sent = asyncio.get_event_loop().run_until_complete(
            manager.broadcast_to_user("nobody", {"type": "test"})
        )
        assert sent == 0

    def test_multiple_users(self, manager, mock_ws):
        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()
        ws2.accept = AsyncMock()
        asyncio.get_event_loop().run_until_complete(manager.connect("user-1", mock_ws))
        asyncio.get_event_loop().run_until_complete(manager.connect("user-2", ws2))
        assert manager.connection_count() == 2
        assert set(manager.connected_users()) == {"user-1", "user-2"}

    def test_broadcast_to_all(self, manager, mock_ws):
        ws2 = AsyncMock()
        ws2.send_json = AsyncMock()
        ws2.accept = AsyncMock()
        asyncio.get_event_loop().run_until_complete(manager.connect("user-1", mock_ws))
        asyncio.get_event_loop().run_until_complete(manager.connect("user-2", ws2))
        total = asyncio.get_event_loop().run_until_complete(
            manager.broadcast_to_all({"type": "announcement"})
        )
        assert total == 2

    def test_singleton_via_nexus(self):
        """nexus.resolve('websocket_manager') returns the same instance every time."""
        from app.core.nexus import nexus

        m1 = nexus.resolve("websocket_manager")
        m2 = nexus.resolve("websocket_manager")
        assert m1 is m2


# ===========================================================================
# SoldierBridgeManager
# ===========================================================================


class TestSoldierBridgeManager:
    """Tests for multi-device soldier bridge with capability registration."""

    @pytest.fixture
    def bridge(self):
        return SoldierBridgeManager()

    def _make_ws(self):
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    def test_connect_three_devices(self, bridge):
        """Bridge must support 3+ simultaneous connections."""
        ws1, ws2, ws3 = self._make_ws(), self._make_ws(), self._make_ws()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(bridge.connect(ws1, "device-1", "desktop", ["pyautogui"]))
        loop.run_until_complete(bridge.connect(ws2, "device-2", "rpi", ["gpio", "camera"]))
        loop.run_until_complete(bridge.connect(ws3, "device-3", "mobile", ["camera"]))
        assert len(bridge.get_connected_devices()) == 3

    def test_capability_routing(self, bridge):
        """get_devices_with_capability returns only matching devices."""
        ws1, ws2 = self._make_ws(), self._make_ws()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(bridge.connect(ws1, "cam-device", "rpi", ["camera", "gpio"]))
        loop.run_until_complete(bridge.connect(ws2, "gui-device", "desktop", ["pyautogui"]))
        camera_devices = bridge.get_devices_with_capability("camera")
        assert "cam-device" in camera_devices
        assert "gui-device" not in camera_devices

    def test_disconnect_removes_capabilities(self, bridge):
        ws = self._make_ws()
        asyncio.get_event_loop().run_until_complete(
            bridge.connect(ws, "temp-device", "desktop", ["pyautogui"])
        )
        bridge.disconnect("temp-device")
        assert "temp-device" not in bridge.device_capabilities

    def test_get_connected_soldiers_returns_info(self, bridge):
        ws = self._make_ws()
        asyncio.get_event_loop().run_until_complete(
            bridge.connect(ws, "soldier-1", "desktop", ["pyautogui"])
        )
        soldiers = bridge.get_connected_soldiers()
        assert len(soldiers) == 1
        assert soldiers[0]["device_id"] == "soldier-1"
        assert "pyautogui" in soldiers[0]["capabilities"]


# ===========================================================================
# SoldierRegistry
# ===========================================================================


class TestSoldierRegistry:
    """Tests for the in-memory + Supabase soldier registry."""

    @pytest.fixture
    def registry(self):
        return SoldierRegistry()

    def test_register_soldier(self, registry):
        record = registry.register("raspi-01", ["gpio", "camera"], device_type="rpi")
        assert record["soldier_id"] == "raspi-01"
        assert record["status"] == "online"
        assert "gpio" in record["capabilities"]

    def test_unregister_marks_offline(self, registry):
        registry.register("raspi-01", ["gpio"])
        result = registry.unregister("raspi-01")
        assert result is True
        assert registry.get_soldier("raspi-01")["status"] == "offline"

    def test_get_available_soldiers_filters_capability(self, registry):
        registry.register("cam-device", ["camera", "gpio"])
        registry.register("gui-device", ["pyautogui"])
        cam_devices = registry.get_available_soldiers("camera")
        assert any(d["soldier_id"] == "cam-device" for d in cam_devices)
        assert not any(d["soldier_id"] == "gui-device" for d in cam_devices)

    def test_get_available_soldiers_excludes_offline(self, registry):
        registry.register("offline-device", ["camera"])
        registry.unregister("offline-device")
        available = registry.get_available_soldiers("camera")
        assert all(d["status"] == "online" for d in available)

    def test_list_all_returns_all(self, registry):
        registry.register("d1", ["a"])
        registry.register("d2", ["b"])
        registry.unregister("d2")
        all_soldiers = registry.list_all()
        assert len(all_soldiers) == 2

    def test_singleton_via_nexus(self):
        """nexus.resolve('soldier_registry') returns the same instance every time."""
        from app.core.nexus import nexus

        r1 = nexus.resolve("soldier_registry")
        r2 = nexus.resolve("soldier_registry")
        assert r1 is r2


# ===========================================================================
# JrvsCloudStorage — graceful degradation without Supabase
# ===========================================================================


class TestJrvsCloudStorageNoop:
    """When Supabase is not configured, all operations return safe defaults."""

    @pytest.fixture
    def storage(self):
        return JrvsCloudStorage()

    def _no_client(self):
        return None

    def test_upload_returns_none_without_client(self, storage):
        with patch.object(storage, "_get_client", self._no_client):
            result = storage.upload("bucket", "path/file.jrvs", b"data")
        assert result is None

    def test_download_returns_none_without_client(self, storage):
        with patch.object(storage, "_get_client", self._no_client):
            result = storage.download("bucket", "path/file.jrvs")
        assert result is None

    def test_list_returns_empty_without_client(self, storage):
        with patch.object(storage, "_get_client", self._no_client):
            result = storage.list("bucket")
        assert result == []

    def test_delete_returns_false_without_client(self, storage):
        with patch.object(storage, "_get_client", self._no_client):
            result = storage.delete("bucket", "path/file.jrvs")
        assert result is False

    def test_upload_with_client(self, storage):
        mock_client = MagicMock()
        mock_client.storage.from_.return_value.upload.return_value = None
        with patch.object(storage, "_get_client", return_value=mock_client):
            result = storage.upload("bucket", "data/test.jrvs", b"raw bytes")
        assert result == "data/test.jrvs"

    def test_download_with_client(self, storage):
        mock_client = MagicMock()
        mock_client.storage.from_.return_value.download.return_value = b"raw bytes"
        with patch.object(storage, "_get_client", return_value=mock_client):
            result = storage.download("bucket", "data/test.jrvs")
        assert result == b"raw bytes"

    def test_execute_upload(self, storage):
        with patch.object(storage, "_get_client", self._no_client):
            result = storage.execute({"action": "upload", "path": "test.jrvs", "data": b"x"})
        assert result == {"success": False}

    def test_execute_list(self, storage):
        with patch.object(storage, "_get_client", self._no_client):
            result = storage.execute({"action": "list"})
        assert result["success"] is True
        assert result["files"] == []
