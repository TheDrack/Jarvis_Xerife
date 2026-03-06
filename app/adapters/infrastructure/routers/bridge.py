# -*- coding: utf-8 -*-
"""Bridge router: /v1/local-bridge/* WebSocket and REST endpoints.

Uses :class:`~app.adapters.infrastructure.soldier_bridge.SoldierBridgeManager`
which supports multiple simultaneous connections and capability registration.
All components are resolved through the Nexus DI container.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.nexus import nexus

logger = logging.getLogger(__name__)


def create_bridge_router() -> APIRouter:
    """
    Create the soldier-bridge router for GUI/edge delegation to connected devices.

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.websocket("/v1/local-bridge")
    async def local_bridge_websocket(
        websocket: WebSocket,
        device_id: str = "default",
        device_type: str = "desktop",
        capabilities: Optional[str] = None,
    ):
        """
        WebSocket endpoint for connecting a soldier device to JARVIS.

        Enables JARVIS (in the cloud) to delegate GUI tasks (PyAutoGUI) or
        mobile-specific tasks (camera, sensors, vibration) to connected devices.
        Supports 3+ simultaneous connections.

        Query Parameters:
            device_id:    Unique identifier for the device (default: "default")
            device_type:  Type of device – desktop, mobile, tablet, rpi, iot, …
            capabilities: Comma-separated capability tags, e.g. "pyautogui,camera"

        Usage:
            Desktop: ws://jarvis-host/v1/local-bridge?device_id=my_pc&device_type=desktop
            Mobile:  ws://jarvis-host/v1/local-bridge?device_id=my_phone&device_type=mobile&capabilities=camera
        """
        bridge_manager = nexus.resolve("soldier_bridge")
        caps: List[str] = [c.strip() for c in capabilities.split(",")] if capabilities else []
        try:
            await bridge_manager.connect(websocket, device_id, device_type, caps)
            while True:
                try:
                    data = await websocket.receive_json()
                    await bridge_manager.handle_message(device_id, data)
                except WebSocketDisconnect:
                    logger.info(f"Device disconnected: {device_id}")
                    break
                except Exception as e:
                    logger.error(f"Error handling message from {device_id}: {e}")
                    await websocket.send_json({"type": "error", "error": str(e)})
        finally:
            bridge_manager.disconnect(device_id)

    @router.get("/v1/local-bridge/devices")
    async def list_connected_devices() -> Dict[str, Any]:
        """List all currently connected soldier devices and their capabilities."""
        bridge_manager = nexus.resolve("soldier_bridge")
        soldiers = bridge_manager.get_connected_soldiers()
        return {"connected_devices": soldiers, "count": len(soldiers)}

    @router.post("/v1/local-bridge/send-task")
    async def send_task_to_local_device(device_id: str, task: Dict[str, Any]) -> Any:
        """
        Send a task to a connected soldier device.

        Args:
            device_id: Target device ID
            task:      Task definition with 'action' and 'parameters'

        Returns:
            Task result from the device
        """
        bridge_manager = nexus.resolve("soldier_bridge")
        if not bridge_manager.is_device_connected(device_id):
            raise HTTPException(
                status_code=404,
                detail=f"Device {device_id} is not connected",
            )
        return await bridge_manager.send_task(device_id, task)

    return router
