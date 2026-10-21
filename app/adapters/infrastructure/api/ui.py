# -*- coding: utf-8 -*-
"""UI endpoints for the Jarvis API server.

Serves the J.A.R.V.I.S. Strategic HUD single-page interface. The HTML lives in
``static/index.html`` (the repository root's ``static/`` directory) instead of
being embedded in Python source, keeping ``api_server`` focused on transport
and business routing.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

logger = __import__("logging").getLogger(__name__)

# static/index.html lives four levels up from this file:
# app/adapters/infrastructure/api/ui.py -> repo root/static
STATIC_INDEX_PATH = Path(__file__).resolve().parents[4] / "static" / "index.html"


def _load_index_html() -> str:
    """Load the HUD HTML from disk (kept out of Python source)."""
    try:
        return STATIC_INDEX_PATH.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive
        logger.error(f"Failed to load {STATIC_INDEX_PATH}: {exc}")
        return "<h1>J.A.R.V.I.S. UI unavailable</h1>"


INDEX_HTML = _load_index_html()


def register_ui_routes(app: FastAPI) -> None:
    """Register the root UI routes on the given FastAPI app."""

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """
        Root endpoint - Stark Industries command interface
        Serves the main HTML UI for interacting with Jarvis with authentication and voice input
        """
        return HTMLResponse(content=INDEX_HTML)

    @app.head("/")
    async def root_head():
        """
        HEAD endpoint for health checks
        Used by monitoring services and browsers to verify server status
        """
        return Response(status_code=200)
