# -*- coding: utf-8 -*-
"""SecretsProvider port - abstract interface for secret retrieval.

All secret/credential access in the application MUST go through this port.
No module other than adapters implementing this interface may use
``os.environ`` directly for secret retrieval.
"""

from abc import ABC, abstractmethod
from typing import Optional


class SecretsProvider(ABC):
    """Port: abstract interface for retrieving application secrets.

    Implementations handle the actual source of secrets (environment
    variables, Vault, AWS Secrets Manager, etc.) while keeping the rest
    of the application decoupled from that source.
    """

    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        """Retrieve the secret value associated with *key*.

        Args:
            key: The name of the secret (e.g. ``"GEMINI_API_KEY"``).

        Returns:
            The secret value as a string, or ``None`` if not found.
        """
