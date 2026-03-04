# -*- coding: utf-8 -*-
"""EnvSecretsProvider - SecretsProvider adapter backed by environment variables.

This is the only module in the project that is allowed to read ``os.environ``
for secret retrieval.  All other modules must depend on the
:class:`~app.ports.secrets_provider.SecretsProvider` port instead.

Implements :class:`app.core.nexuscomponent.NexusComponent` so it can be
resolved via ``nexus.resolve("env_secrets_provider")``.
"""

import logging
import os
from typing import Any, Dict, Optional

from app.core.nexuscomponent import NexusComponent
from app.ports.secrets_provider import SecretsProvider

logger = logging.getLogger(__name__)


class EnvSecretsProvider(SecretsProvider, NexusComponent):
    """Reads secrets from the process environment (``os.environ``).

    Implements both :class:`SecretsProvider` (port contract) and
    :class:`NexusComponent` (Nexus resolvability contract).

    This adapter is the single authorised entry point for environment-based
    secret access.  It can be swapped for a Vault/SSM adapter in production
    without touching any other module.
    """

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retrieve a secret described by *context*.

        Expected context keys:
            - ``key`` (str): Name of the secret / environment variable.

        Returns:
            ``{"success": True, "value": "<secret>"}`` when found.
            ``{"success": False, "error": "..."}`` otherwise.
        """
        ctx = context or {}
        key = ctx.get("key", "")
        if not key:
            return {"success": False, "error": "Campo 'key' obrigatório no contexto."}

        value = self.get_secret(key)
        if value is None:
            return {"success": False, "error": f"Segredo '{key}' não encontrado."}
        return {"success": True, "value": value}

    # ------------------------------------------------------------------
    # SecretsProvider interface
    # ------------------------------------------------------------------

    def get_secret(self, key: str) -> Optional[str]:
        """Return the environment variable named *key*, or ``None``.

        Args:
            key: Environment variable name (case-sensitive on most systems).

        Returns:
            The value of the environment variable, or ``None`` if unset.
        """
        value = os.environ.get(key)
        if value is None:
            logger.debug("🔑 [SecretsProvider] Chave '%s' não encontrada no ambiente.", key)
        return value
