# -*- coding: utf-8 -*-
"""OsintProvider port - abstract interface for OSINT search engines.

All OSINT search operations MUST go through this port.
No module other than adapters implementing this interface may call
external OSINT services directly.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class OsintProvider(ABC):
    """Port: abstract interface for Open Source Intelligence (OSINT) searches.

    Implementations handle the actual OSINT engine (Eagle OSINT, Maltego, etc.)
    while keeping the rest of the application decoupled from that engine.
    """

    @abstractmethod
    def search(self, query: str) -> Dict[str, Any]:
        """Perform an OSINT search for *query*.

        Args:
            query: Target identifier (email, username, phone, domain, etc.).

        Returns:
            Structured dictionary with OSINT results.

        Raises:
            RuntimeError: If the OSINT engine call fails.
        """
