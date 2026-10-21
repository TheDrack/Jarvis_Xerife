# -*- coding: utf-8 -*-
"""API route modules split out of api_server.py (god-file decomposition)."""

from app.adapters.infrastructure.api.ui import register_ui_routes

__all__ = ["register_ui_routes"]
