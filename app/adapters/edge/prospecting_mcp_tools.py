"""Session-authorized MCP tools for Jarvis Prospecto.

All calls pass through the canonical ToolDispatcher so manifest validation,
rate limiting, authorization, output-schema validation and audit are enforced.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.adapters.infrastructure.session_authorization import SESSION_GATEWAY
from app.runtime.toolbox import (
    HostToolAuthorizationPolicy,
    JsonlToolAuditSink,
    ToolDispatcher,
    ToolRegistry,
    TrustedToolPrincipal,
)

logger = logging.getLogger(__name__)
PROSPECTING_CAPABILITY = "prospecting.cnpj.read"
PROSPECTING_TOOLS = (
    "prospecting.companies.search",
    "prospecting.companies.lookup",
)


def _build_dispatcher(
    *,
    session_gateway: Any,
    event_sink: Any = None,
) -> ToolDispatcher:
    """Build a local dispatcher whose principal is resolved from paired session state."""

    def resolve_principal() -> TrustedToolPrincipal:
        session = session_gateway.require(PROSPECTING_CAPABILITY)
        return TrustedToolPrincipal(
            principal_id="local-owner",
            session_id=session["session_id"],
            capabilities=frozenset({session["capability"]}),
        )

    authorizer = HostToolAuthorizationPolicy(principal_resolver=resolve_principal)
    return ToolDispatcher(
        ToolRegistry.from_file(),
        authorizer=authorizer,
        event_sink=event_sink if event_sink is not None else JsonlToolAuditSink(),
    )


def _safe_failure(result: Any) -> dict[str, Any]:
    code = getattr(result, "error_code", None) or "prospecting_dispatch_failed"
    messages = {
        "authorization_denied": "A sessão local não possui a capability de leitura do Prospecto. Refaça o pareamento com o perfil termux_jarvis.",
        "adapter_precondition_failed": "A base CNPJ não está configurada ou disponível neste host.",
        "invalid_arguments": "Os filtros informados não atendem ao contrato da pesquisa.",
        "invalid_output": "O adaptador retornou dados fora do contrato declarado.",
        "rate_limited": "Limite de consultas do Prospecto atingido; aguarde antes de repetir.",
        "tool_not_found": "A ferramenta Prospecto não está registrada neste runtime.",
    }
    return {
        "success": False,
        "error_code": code,
        "message": messages.get(code, "A operação Prospecto não foi concluída."),
        "retryable": bool(getattr(result, "retryable", False)),
        "retry_after_seconds": getattr(result, "retry_after_seconds", None),
    }


def register_prospecting_tools(
    mcp: Any,
    *,
    dispatcher: Any = None,
    session_gateway: Any = None,
    event_sink: Any = None,
) -> tuple[str, ...]:
    """Register bounded company search and exact CNPJ lookup through ToolDispatcher."""
    tool_dispatcher = dispatcher or _build_dispatcher(
        session_gateway=session_gateway if session_gateway is not None else SESSION_GATEWAY,
        event_sink=event_sink,
    )

    @mcp.tool(name="prospecting.companies.search")
    async def prospecting_companies_search(
        uf: str,
        cnae_prefixes: list[str],
        municipalities: Optional[list[str]] = None,
        only_active: bool = True,
        include_secondary_cnae: bool = True,
        limit: int = 50,
        after_cnpj_basico: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search Brazilian companies by UF, municipality and CNAE.

        Results are grouped by the 8-digit CNPJ root. This is discovery only;
        it does not contact companies or expose personal contact data.
        """
        try:
            result = await tool_dispatcher.dispatch_async(
                {
                    "tool_id": "prospecting.companies.search",
                    "tool_version": "1.0.0",
                    "capability": "prospecting.companies.search",
                    "arguments": {
                        "uf": uf,
                        "cnae_prefixes": cnae_prefixes,
                        "municipalities": municipalities,
                        "only_active": only_active,
                        "include_secondary_cnae": include_secondary_cnae,
                        "limit": limit,
                        "after_cnpj_basico": after_cnpj_basico,
                    },
                    "caller": "android_mcp",
                    "scope": "local",
                }
            )
            return result.output if result.success else _safe_failure(result)
        except Exception:
            logger.exception("Jarvis Prospecto MCP search dispatch failed")
            return {
                "success": False,
                "error_code": "prospecting_dispatch_failed",
                "message": "A pesquisa Prospecto não pôde ser despachada.",
                "retryable": False,
            }

    @mcp.tool(name="prospecting.companies.lookup")
    async def prospecting_company_lookup(cnpj: str) -> dict[str, Any]:
        """Look up one exact 14-digit CNPJ establishment in the official dataset."""
        try:
            result = await tool_dispatcher.dispatch_async(
                {
                    "tool_id": "prospecting.companies.lookup",
                    "tool_version": "1.0.0",
                    "capability": "prospecting.companies.lookup",
                    "arguments": {"cnpj": cnpj},
                    "caller": "android_mcp",
                    "scope": "local",
                }
            )
            return result.output if result.success else _safe_failure(result)
        except Exception:
            logger.exception("Jarvis Prospecto MCP lookup dispatch failed")
            return {
                "success": False,
                "error_code": "prospecting_dispatch_failed",
                "message": "A consulta de CNPJ não pôde ser despachada.",
                "retryable": False,
            }

    return PROSPECTING_TOOLS


__all__ = ["register_prospecting_tools", "PROSPECTING_CAPABILITY", "PROSPECTING_TOOLS"]
