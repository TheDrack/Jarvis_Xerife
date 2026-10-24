# -*- coding: utf-8 -*-
"""Bridge router: /v1/local-bridge/* WebSocket and REST endpoints.

Mobile clients must authenticate with a valid Jarvis bearer token. Their bridge
IDs are namespaced by the authenticated principal to prevent cross-user ID
collisions. Existing non-mobile bridge clients retain their current contract.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect

from app.core.nexus import nexus

logger = logging.getLogger(__name__)


def create_bridge_router() -> APIRouter:
    """Create the soldier-bridge router."""
    router = APIRouter()

    async def require_authenticated_principal(
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        """Validate bearer tokens for HTTP bridge management and task dispatch."""
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status_code=401, detail="Bearer token required")
        try:
            auth_adapter = nexus.resolve("auth_adapter")
            claims = auth_adapter.verify_token(token.strip())
        except Exception:
            claims = None
        if not isinstance(claims, dict) or not (claims.get("user_id") or claims.get("sub")):
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return claims

    @router.websocket("/v1/local-bridge")
    async def local_bridge_websocket(
        websocket: WebSocket,
        device_id: str = "default",
        device_type: str = "desktop",
        capabilities: Optional[str] = None,
    ):
        """Connect an edge device. Mobile clients must provide Authorization: Bearer <JWT>."""
        bridge_manager = nexus.resolve("soldier_bridge")
        canonical_device_id = device_id
        if device_type.lower() == "mobile":
            authorization = websocket.headers.get("authorization", "")
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not token.strip():
                await websocket.close(code=4401, reason="Authentication required")
                return
            if not device_id or device_id == "default" or len(device_id) > 128:
                await websocket.close(code=4400, reason="A valid mobile device_id is required")
                return
            if any(ord(char) < 32 for char in device_id):
                await websocket.close(code=4400, reason="Invalid mobile device_id")
                return
            try:
                auth_adapter = nexus.resolve("auth_adapter")
                claims = auth_adapter.verify_token(token.strip())
            except Exception:
                claims = None
            principal = None
            if isinstance(claims, dict):
                principal = claims.get("user_id") or claims.get("sub")
            if not isinstance(principal, (str, int)) or not str(principal).strip():
                await websocket.close(code=4401, reason="Invalid authentication token")
                return
            canonical_device_id = "mobile:" + str(principal) + ":" + device_id

        caps: List[str] = [c.strip() for c in capabilities.split(",") if c.strip()] if capabilities else []
        try:
            await bridge_manager.connect(websocket, canonical_device_id, device_type, caps)
            while True:
                try:
                    data = await websocket.receive_json()
                    await bridge_manager.handle_message(canonical_device_id, data)
                except WebSocketDisconnect:
                    logger.info("Device disconnected: %s", canonical_device_id)
                    break
                except Exception:
                    logger.exception("Error handling bridge message from %s", canonical_device_id)
                    await websocket.send_json({"type": "error", "error": "Message handling failed"})
        finally:
            bridge_manager.disconnect(canonical_device_id)

    @router.get("/v1/local-bridge/devices")
    async def list_connected_devices(
        _principal: Dict[str, Any] = Depends(require_authenticated_principal),
    ) -> Dict[str, Any]:
        """List all currently connected soldier devices and their capabilities."""
        bridge_manager = nexus.resolve("soldier_bridge")
        principal = str(_principal.get("user_id") or _principal.get("sub"))
        soldiers = [
            soldier for soldier in bridge_manager.get_connected_soldiers()
            if not str(soldier.get("device_id", "")).startswith("mobile:")
            or str(soldier.get("device_id", "")).startswith("mobile:" + principal + ":")
        ]
        return {"connected_devices": soldiers, "count": len(soldiers)}

    @router.post("/v1/local-bridge/send-task")
    async def send_task_to_local_device(
        device_id: str,
        task: Dict[str, Any],
        _principal: Dict[str, Any] = Depends(require_authenticated_principal),
    ) -> Any:
        """Send a task to a connected soldier device using the configured server key."""
        principal = str(_principal.get("user_id") or _principal.get("sub"))
        if device_id.startswith("mobile:") and not device_id.startswith("mobile:" + principal + ":"):
            raise HTTPException(status_code=403, detail="Device belongs to another user")
        bridge_manager = nexus.resolve("soldier_bridge")
        if not bridge_manager.is_device_connected(device_id):
            raise HTTPException(status_code=404, detail=f"Device {device_id} is not connected")
        # Mobile speech/notification clients do not execute local desktop commands
        # and must never receive the server's local-bridge secret.
        if device_id.startswith("mobile:"):
            api_key = None
        else:
            api_key = os.getenv("API_KEY_LOCAL")
            if not api_key:
                raise HTTPException(status_code=503, detail="API_KEY_LOCAL não configurada no servidor.")
        return await bridge_manager.send_task(device_id, task, api_key=api_key)

    return router
