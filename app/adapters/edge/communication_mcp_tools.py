"""Read-only MCP discovery tools for installed communication adapters."""

from __future__ import annotations

from typing import Any

from app.communication.registry import CommunicationRegistry


def register_communication_tools(
    mcp: Any, registry: CommunicationRegistry
) -> tuple[str, ...]:
    """Expose adapter metadata without exposing credentials or invoking adapters."""

    @mcp.tool(name="communication_adapters_list")
    def communication_adapters_list() -> dict[str, Any]:
        """List installed communication adapters, protocols, and operations."""
        return {"success": True, "adapters": registry.describe_adapters()}

    return ("communication_adapters_list",)
