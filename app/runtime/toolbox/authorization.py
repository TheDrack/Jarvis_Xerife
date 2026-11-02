"""Trusted authorization port for universal tool execution."""

from __future__ import annotations

from typing import Awaitable, Protocol

from app.runtime.toolbox.contracts import (
    ToolAuthorizationDecision,
    ToolManifest,
    ToolRequest,
)


class ToolAuthorizationPolicy(Protocol):
    """Host-provided policy that resolves identity and verifies scoped approvals.

    Implementations must derive the principal/session from authenticated host
    context, not from ToolRequest.caller, and must verify approval references
    against a trusted approval source before returning a granted decision.
    """

    def authorize_tool(
        self,
        request: ToolRequest,
        manifest: ToolManifest,
    ) -> ToolAuthorizationDecision | Awaitable[ToolAuthorizationDecision]:
        """Return a decision bound to this exact request."""
        ...
