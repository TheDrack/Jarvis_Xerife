# -*- coding: utf-8 -*-
"""Supabase client singleton for JARVIS.

Provides a lazily-initialised Supabase client that is shared across all
adapters.  When ``SUPABASE_URL`` or ``SUPABASE_KEY`` are not set the module
degrades gracefully so the rest of the system keeps working without cloud
connectivity.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from supabase import Client, create_client

    _SUPABASE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SUPABASE_AVAILABLE = False
    Client = None  # type: ignore[assignment,misc]
    logger.warning("⚠️ [Supabase] supabase-py não instalado. Funcionalidades cloud desabilitadas.")

_client: Optional["Client"] = None  # type: ignore[type-arg]


def get_supabase_client() -> Optional["Client"]:  # type: ignore[type-arg]
    """Return the shared Supabase :class:`Client`, or ``None`` if unavailable.

    The client is created once (lazily) using ``SUPABASE_URL`` and
    ``SUPABASE_KEY`` from the application settings.  Subsequent calls return
    the cached instance.

    Returns:
        Initialised :class:`supabase.Client` or ``None`` when Supabase is not
        configured or the ``supabase`` package is not installed.
    """
    global _client

    if _client is not None:
        return _client

    if not _SUPABASE_AVAILABLE:
        return None

    from app.core.config import settings  # lazy to avoid circular imports

    url = settings.supabase_url
    key = settings.supabase_key

    if not url or not key:
        logger.debug("[Supabase] SUPABASE_URL / SUPABASE_KEY não configuradas; cliente desabilitado.")
        return None

    try:
        _client = create_client(url, key)
        logger.info("✅ [Supabase] Cliente inicializado para %s", url)
    except Exception as exc:
        logger.error("❌ [Supabase] Falha ao inicializar cliente: %s", exc)
        return None

    return _client


def is_supabase_available() -> bool:
    """Return ``True`` if the Supabase client is reachable."""
    return get_supabase_client() is not None
