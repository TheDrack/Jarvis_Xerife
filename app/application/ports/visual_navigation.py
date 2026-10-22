"""Port for local visual desktop navigation."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class VisualNavigationPort(Protocol):
    """Contract implemented by a local visual-navigation adapter."""

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Observe the screen or execute a verified template-based recipe."""
        ...
