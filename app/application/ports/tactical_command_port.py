# -*- coding: utf-8 -*-
"""Tactical Command Port - Interface for C2 security payload execution."""

from abc import abstractmethod
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent


class TacticalCommandPort(NexusComponent):
    """
    Port (interface) for dispatching security audit payloads to Soldier nodes.

    Implementations must route the request to the appropriate Soldier and
    return the raw result produced by the requested tool.

    All operations are scoped to ``target_scope`` which must represent
    user-owned assets (e.g. a home network CIDR or a specific IP address).
    """

    def execute(self, context: Optional[Dict] = None) -> Dict:
        """NexusComponent entry point — delegates to execute_security_payload."""
        ctx = context or {}
        node_id = ctx.get("node_id")
        tool = ctx.get("tool")
        target_scope = ctx.get("target_scope")
        if not node_id or not tool or not target_scope:
            return {
                "success": False,
                "error": "Context must contain 'node_id', 'tool', and 'target_scope'.",
            }
        return self.execute_security_payload(node_id, tool, target_scope)

    @abstractmethod
    def execute_security_payload(
        self,
        node_id: str,
        tool: str,
        target_scope: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch a security audit payload to the specified Soldier node.

        Args:
            node_id: The unique identifier of the target Soldier.
            tool: Name of the security tool to invoke (e.g. ``"nmap"``,
                ``"arp_scan"``, ``"heartbeat"``).
            target_scope: Network scope / IP range that defines the boundary
                of the audit (must be user-owned, e.g. ``"192.168.1.0/24"``).
            options: Optional key-value parameters forwarded to the tool.

        Returns:
            A dict with at minimum ``success`` (bool) and ``node_id`` keys,
            plus tool-specific output under the ``result`` key.
        """
