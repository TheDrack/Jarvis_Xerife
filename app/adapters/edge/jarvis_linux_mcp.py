"""Authenticated Linux-only entrypoint for the optional desktop MCP server."""
from __future__ import annotations

import contextlib
import os

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from app.adapters.edge.jarvis_desktop_mcp import mcp
from app.adapters.infrastructure.mcp_bearer_auth import BearerAuthMiddleware


def create_app(token: str) -> Starlette:
    """Build the Streamable HTTP app with a mandatory bearer-token boundary."""

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette):
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[Mount("/", app=BearerAuthMiddleware(mcp.streamable_http_app(), token))],
        lifespan=lifespan,
    )


def main() -> None:
    token = os.environ.get("JARVIS_DESKTOP_AUTH_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError(
            "JARVIS_DESKTOP_AUTH_TOKEN ausente ou curto; execute o provisionador para gerar um token."
        )
    port = int(os.environ.get("JARVIS_DESKTOP_HTTP_PORT", "8765"))
    uvicorn.run(
        create_app(token),
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
