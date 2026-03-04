# -*- coding: utf-8 -*-
"""EnvSecretsProvider - SecretsProvider adapter backed by environment variables.

This is the only module in the project that is allowed to read ``os.environ``
for secret retrieval.  All other modules must depend on the
:class:`~app.ports.secrets_provider.SecretsProvider` port instead.
"""

import logging
import os
from typing import Optional

from app.ports.secrets_provider import SecretsProvider

logger = logging.getLogger(__name__)


class EnvSecretsProvider(SecretsProvider):
    """Reads secrets from the process environment (``os.environ``).

    This adapter is the single authorised entry point for environment-based
    secret access.  It can be swapped for a Vault/SSM adapter in production
    without touching any other module.
    """

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
