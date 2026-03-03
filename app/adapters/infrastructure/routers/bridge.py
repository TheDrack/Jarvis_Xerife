# -*- coding: utf-8 -*-
"""Bridge router: /v1/local-bridge/* WebSocket and REST endpoints."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def create_bridge_router() -> APIRouter:
    """
    Create the local-bridge router for GUI delegation to connected devices.

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.websocket("/v1/local-bridge")
    async def local_bridge_websocket(
        websocket: WebSocket,
        device_id: str = "default",
        device_type: str = "desktop",
    ):
        """
        WebSocket endpoint for connecting a local PC or mobile device to JARVIS.

        Enables JARVIS (in the cloud) to delegate GUI tasks (PyAutoGUI) or
        mobile-specific tasks (camera, sensors, vibration) to connected devices.

        Query Parameters:
            device_id:   Unique identifier for the device (default: "default")
            device_type: Type of device – desktop, mobile, tablet (default: "desktop")

        Usage:
            Desktop: ws://jarvis-host/v1/local-bridge?device_id=my_pc&device_type=desktop
            Mobile:  ws://jarvis-host/v1/local-bridge?device_id=my_phone&device_type=mobile
        """
        from app.application.services.local_bridge import get_bridge_manager

        bridge_manager = get_bridge_manager()
        try:
            await bridge_manager.connect(websocket, device_id, device_type)
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
        """List all currently connected local devices."""
        from app.application.services.local_bridge import get_bridge_manager

        bridge_manager = get_bridge_manager()
        devices = bridge_manager.get_connected_devices()
        return {"connected_devices": devices, "count": len(devices)}

    @router.post("/v1/local-bridge/send-task")
    async def send_task_to_local_device(device_id: str, task: Dict[str, Any]) -> Any:
        """
        Send a task to a connected local device.

        Args:
            device_id: Target device ID
            task:      Task definition with 'action' and 'parameters'

        Returns:
            Task result from the local device
        """
        from app.application.services.local_bridge import get_bridge_manager

        bridge_manager = get_bridge_manager()
        if not bridge_manager.is_device_connected(device_id):
            raise HTTPException(
                status_code=404,
                detail=f"Device {device_id} is not connected",
            )
        return await bridge_manager.send_task(device_id, task)

    return router
