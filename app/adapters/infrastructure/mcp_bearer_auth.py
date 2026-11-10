"""Small ASGI bearer-token gate for a private, local MCP endpoint."""
from __future__ import annotations

import hmac
from typing import Any, Awaitable, Callable


ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]


class BearerAuthMiddleware:
    """Require exactly one constant-time-checked Authorization bearer header."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("MCP bearer token must contain at least 32 characters")
        self.app = app
        self.expected = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Awaitable[Any]], send: Callable[..., Awaitable[Any]]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        values = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"authorization"
        ]
        if len(values) != 1 or not hmac.compare_digest(values[0], self.expected):
            body = b'{"error":"unauthorized"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"www-authenticate", b"Bearer"),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
