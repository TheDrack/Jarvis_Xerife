# -*- coding: utf-8 -*-
"""WebSocket Manager — per-user real-time connection hub for JARVIS.

Manages active WebSocket connections keyed by ``user_id`` and provides
broadcast helpers so that assistant responses, evolution events and
notifications can be pushed directly to the HUD / frontend instead of
relying on polling.

Typical usage in a FastAPI endpoint::

    manager = get_websocket_manager()

    @app.websocket("/ws/{user_id}")
    async def ws_endpoint(websocket: WebSocket, user_id: str):
        await manager.connect(user_id, websocket)
        try:
            while True:
                msg = await websocket.receive_text()
                # … handle incoming messages …
        except WebSocketDisconnect:
            manager.disconnect(user_id)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class WebSocketManager(NexusComponent):
    """Manages active WebSocket connections per ``user_id``.

    Thread-safety note: FastAPI uses asyncio, so all coroutines must run in
    the same event loop.  The methods here are designed to be called from
    async handlers only.
    """

    def __init__(self) -> None:
        # {user_id: [WebSocket, ...]} — one user can have multiple tabs open
        self._connections: Dict[str, List[WebSocket]] = {}

    def execute(self, context: dict) -> dict:
        """NexusComponent entry-point: broadcast a message to a user."""
        user_id = (context or {}).get("user_id", "")
        message = (context or {}).get("message", {})
        if not user_id or not message:
            return {"success": False, "error": "user_id e message são obrigatórios"}

        # asyncio.run() cannot be used inside a running loop;
        # schedule the coroutine on the existing loop instead.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.broadcast_to_user(user_id, message))
            else:
                loop.run_until_complete(self.broadcast_to_user(user_id, message))
            return {"success": True}
        except Exception as exc:
            logger.error("[WebSocketManager] execute() falhou: %s", exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """Accept *websocket* and register it under *user_id*.

        Args:
            user_id:   Identifier of the user owning this connection.
            websocket: The incoming WebSocket connection.
        """
        await websocket.accept()
        self._connections.setdefault(user_id, []).append(websocket)
        logger.info("🔌 [WS] User %s connected (%d active)", user_id, self.connection_count(user_id))
        await websocket.send_json(
            {
                "type": "connected",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def disconnect(self, user_id: str, websocket: Optional[WebSocket] = None) -> None:
        """Remove *websocket* (or all connections) for *user_id*.

        Args:
            user_id:   User whose connection is being removed.
            websocket: Specific socket to remove.  When ``None``, ALL
                       connections for *user_id* are removed.
        """
        if user_id not in self._connections:
            return
        if websocket is None:
            del self._connections[user_id]
        else:
            sockets = self._connections[user_id]
            if websocket in sockets:
                sockets.remove(websocket)
            if not sockets:
                del self._connections[user_id]
        logger.info("🔌 [WS] User %s disconnected", user_id)

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def broadcast_to_user(self, user_id: str, message: Any) -> int:
        """Send *message* to every active connection of *user_id*.

        Args:
            user_id: Target user.
            message: Payload — serialised as JSON if it is a dict/list.

        Returns:
            Number of connections that received the message successfully.
        """
        sockets = list(self._connections.get(user_id, []))
        if not sockets:
            logger.debug("[WS] No active connections for user %s", user_id)
            return 0

        sent = 0
        dead: List[WebSocket] = []
        for ws in sockets:
            try:
                if isinstance(message, (dict, list)):
                    await ws.send_json(message)
                else:
                    await ws.send_text(str(message))
                sent += 1
            except Exception as exc:
                logger.warning("[WS] Send to %s failed: %s", user_id, exc)
                dead.append(ws)

        for ws in dead:
            self.disconnect(user_id, ws)

        return sent

    async def broadcast_to_all(self, message: Any) -> int:
        """Send *message* to every connected user.

        Args:
            message: Payload — serialised as JSON if it is a dict/list.

        Returns:
            Total number of successful sends.
        """
        total = 0
        for user_id in list(self._connections.keys()):
            total += await self.broadcast_to_user(user_id, message)
        return total

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def connection_count(self, user_id: Optional[str] = None) -> int:
        """Return the number of active connections.

        Args:
            user_id: When given, count only this user's connections.

        Returns:
            Connection count.
        """
        if user_id is not None:
            return len(self._connections.get(user_id, []))
        return sum(len(sockets) for sockets in self._connections.values())

    def connected_users(self) -> List[str]:
        """Return a list of currently connected user IDs."""
        return list(self._connections.keys())

    def is_connected(self, user_id: str) -> bool:
        """Return ``True`` if *user_id* has at least one active connection."""
        return bool(self._connections.get(user_id))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Return the global :class:`WebSocketManager` singleton."""
    global _manager
    if _manager is None:
        _manager = WebSocketManager()
    return _manager
