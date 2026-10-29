"""Optional Respan tracing initialization for direct Python LLM SDK calls.

The open-source respan-gateway has its own tracing plugin; see docs/RESPAN_SETUP.md.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)
_respan_instance: Any = None
_initialization_attempted = False


def initialize_respan_tracing() -> Any:
    """Initialize tracing once, before creating provider SDK clients.

    Missing credentials or an unavailable optional package never prevents Jarvis
    from starting. Gateway request tracing is configured separately in gateway.toml.
    """
    global _respan_instance, _initialization_attempted
    if _initialization_attempted:
        return _respan_instance
    _initialization_attempted = True

    if not os.getenv("RESPAN_API_KEY", "").strip():
        logger.info("Respan tracing skipped: RESPAN_API_KEY is not configured.")
        return None

    try:
        from respan import Respan
        _respan_instance = Respan()
        logger.info("Respan tracing initialized.")
        return _respan_instance
    except Exception as exc:  # observability must not take down the assistant
        logger.warning("Respan tracing unavailable (%s); continuing without tracing.", type(exc).__name__)
        _respan_instance = None
        return None


def shutdown_respan_tracing() -> None:
    """Flush and stop the SDK during graceful shutdown, when initialized."""
    global _respan_instance
    instance, _respan_instance = _respan_instance, None
    if instance is not None:
        try:
            instance.shutdown()
        except Exception as exc:
            logger.warning("Respan tracing shutdown failed (%s).", type(exc).__name__)
