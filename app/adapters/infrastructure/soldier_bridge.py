# -*- coding: utf-8 -*-
"""Soldier Bridge — WebSocket hub for multiple edge devices (soldiers).

Extends :class:`~app.application.services.local_bridge.LocalBridgeManager`
with:

- Support for 3+ simultaneous device connections.
- Per-device capability registration (beyond desktop/mobile/tablet).
- Integration with :class:`~app.application.services.soldier_registry.SoldierRegistry`
  so devices are persisted in Supabase / memory.

The module is deliberately backward-compatible with the existing bridge
router: ``get_bridge_manager()`` still works and returns a
:class:`SoldierBridgeManager` instance instead of the old
:class:`LocalBridgeManager`.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

from app.application.services.local_bridge import LocalBridgeManager

logger = logging.getLogger(__name__)


class SoldierBridgeManager(LocalBridgeManager):
    """WebSocket hub that supports **multiple** simultaneous device connections.

    Each connected device (soldier) registers its ``capabilities`` list on
    connect so that :class:`~app.application.services.soldier_registry.SoldierRegistry`
    can route tasks to the appropriate device.

    Accepts **unlimited** concurrent connections (no 1:1 limit).
    """

    def __init__(self) -> None:
        super().__init__()
        # Per-device capability set: {device_id: {cap1, cap2, ...}}
        self.device_capabilities: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Overridden connect/disconnect with capability support
    # ------------------------------------------------------------------

    async def connect(
        self,
        websocket: WebSocket,
        device_id: str,
        device_type: str = "desktop",
        capabilities: Optional[List[str]] = None,
    ) -> None:
        """Accept a WebSocket connection and register the device.

        Args:
            websocket:    Incoming WebSocket connection.
            device_id:    Unique soldier identifier.
            device_type:  Type of device (desktop, mobile, tablet, rpi, iot, …).
            capabilities: Optional list of capability tags supported by this
                          device (e.g. ``["pyautogui", "camera", "gpio"]``).
        """
        await websocket.accept()
        self.active_connections[device_id] = websocket
        self.device_types[device_id] = device_type.lower()
        self.task_queues[device_id] = asyncio.Queue()
        self.device_capabilities[device_id] = set(capabilities or [])

        logger.info(
            "🪖 [SoldierBridge] Device '%s' connected (type=%s, caps=%s, total=%d)",
            device_id,
            device_type,
            list(self.device_capabilities[device_id]),
            len(self.active_connections),
        )

        await websocket.send_json(
            {
                "type": "connected",
                "soldier_id": device_id,
                "device_type": device_type,
                "capabilities_registered": list(self.device_capabilities[device_id]),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }
        )

        # Register with SoldierRegistry (best-effort)
        self._register_with_registry(device_id, device_type, capabilities or [])

    def disconnect(self, device_id: str) -> None:
        """Handle soldier disconnection and update registry."""
        super().disconnect(device_id)
        self.device_capabilities.pop(device_id, None)
        # Update registry (best-effort)
        self._unregister_from_registry(device_id)

    # ------------------------------------------------------------------
    # Capability-aware routing
    # ------------------------------------------------------------------

    def get_devices_with_capability(self, capability: str) -> List[str]:
        """Return IDs of connected devices that advertise *capability*.

        Args:
            capability: Capability tag to look for (e.g. ``"pyautogui"``).

        Returns:
            List of device IDs.
        """
        return [
            did
            for did, caps in self.device_capabilities.items()
            if capability in caps and did in self.active_connections
        ]

    def get_device_capabilities(self, device_id: str) -> List[str]:
        """Return the capability list for *device_id*.

        Args:
            device_id: The target device.

        Returns:
            List of capability tags.
        """
        return list(self.device_capabilities.get(device_id, []))

    def get_connected_soldiers(self) -> List[Dict[str, Any]]:
        """Return info about all connected soldiers.

        Returns:
            List of dicts with ``device_id``, ``device_type``, and
            ``capabilities``.
        """
        return [
            {
                "device_id": did,
                "device_type": self.device_types.get(did, "unknown"),
                "capabilities": list(self.device_capabilities.get(did, [])),
            }
            for did in self.active_connections
        ]

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def _register_with_registry(
        self, device_id: str, device_type: str, capabilities: List[str]
    ) -> None:
        """Push registration to SoldierRegistry via Nexus (non-blocking, best-effort)."""
        try:
            from app.core.nexus import nexus

            registry = nexus.resolve("soldier_registry")
            registry.register(device_id, capabilities, device_type=device_type)
        except Exception as exc:
            logger.debug("[SoldierBridge] Registry register falhou: %s", exc)

    def _unregister_from_registry(self, device_id: str) -> None:
        """Remove device from SoldierRegistry via Nexus when disconnected."""
        try:
            from app.core.nexus import nexus

            registry = nexus.resolve("soldier_registry")
            registry.unregister(device_id)
        except Exception as exc:
            logger.debug("[SoldierBridge] Registry unregister falhou: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton — replaces LocalBridgeManager globally
# ---------------------------------------------------------------------------

_bridge_manager: Optional[SoldierBridgeManager] = None


def get_bridge_manager() -> SoldierBridgeManager:
    """Return the global :class:`SoldierBridgeManager` singleton.

    Backward-compatible replacement for
    :func:`app.application.services.local_bridge.get_bridge_manager`.
    """
    global _bridge_manager
    if _bridge_manager is None:
        _bridge_manager = SoldierBridgeManager()
    return _bridge_manager


# Nexus Compatibility
SoldierBridge = SoldierBridgeManager
