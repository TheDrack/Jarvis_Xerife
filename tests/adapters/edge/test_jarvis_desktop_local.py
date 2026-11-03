from __future__ import annotations

import json
import sys

import pytest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.adapters.edge.jarvis_desktop_local import (
    LocalRuntime,
    _build_uvicorn_config,
    _host_name,
    _is_allowed_address,
    _tailscale_snapshot,
    create_local_app,
)


class _ClientAddressMiddleware:
    """Set the ASGI client address without depending on a Starlette TestClient version."""

    def __init__(self, app, address: str) -> None:
        self.app = app
        self.client = (address, 54321)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope = dict(scope)
            scope["client"] = self.client
        await self.app(scope, receive, send)


def _client(runtime: LocalRuntime, address: str = "127.0.0.1") -> TestClient:
    app = _ClientAddressMiddleware(create_local_app(runtime), address)
    return TestClient(app, base_url=f"http://{address}:8766")


