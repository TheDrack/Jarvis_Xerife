"""Session-authorized MCP tools for Jarvis Prospecto.

Company discovery calls pass through the canonical ToolDispatcher. The active
outreach tools use a separate session capability plus the durable SQLite
approval, suppression, idempotency and audit workflow.
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
        "adapter_not_ready": "A base CNPJ não está configurada ou disponível neste host.",
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
            arguments: dict[str, Any] = {
                "uf": uf.strip().upper(),
                "cnae_prefixes": cnae_prefixes,
                "only_active": only_active,
                "include_secondary_cnae": include_secondary_cnae,
                "limit": limit,
            }
            if municipalities is not None:
                arguments["municipalities"] = municipalities
            if after_cnpj_basico is not None:
                arguments["after_cnpj_basico"] = after_cnpj_basico
            result = await tool_dispatcher.dispatch_async(
                {
                    "tool_id": "prospecting.companies.search",
                    "tool_version": "1.0.0",
                    "capability": PROSPECTING_CAPABILITY,
                    "arguments": arguments,
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
                    "capability": PROSPECTING_CAPABILITY,
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



# Outreach is a separate active capability; existing read-only sessions do not inherit it.
PROSPECTING_OUTREACH_CAPABILITY = "prospecting.outreach.manage"
PROSPECTING_OUTREACH_TOOLS = (
    "prospecting.outreach.plan",
    "prospecting.outreach.approve",
    "prospecting.outreach.dispatch",
    "prospecting.outreach.block",
    "prospecting.outreach.history",
)


def _build_outreach_service():
    import os
    from pathlib import Path
    from app.application.prospecting.outreach import (
        OutreachService, SQLiteOutreachStore, build_webhook_transports_from_env,
    )

    configured = os.getenv("JARVIS_PROSPECTO_OUTREACH_DB", "").strip()
    database = Path(configured).expanduser() if configured else (
        Path.home() / ".local" / "share" / "jarvis" / "prospecto" / "outreach.sqlite3"
    )
    return OutreachService(
        SQLiteOutreachStore(database),
        transports=build_webhook_transports_from_env(),
    )


def register_prospecting_outreach_tools(
    mcp: Any, *, service: Any = None, session_gateway: Any = None,
) -> tuple[str, ...]:
    """Register session-authorized planning, approval, dispatch and DNC tools."""
    from app.application.prospecting.outreach import Channel, ContactAuthorization

    outreach = service if service is not None else _build_outreach_service()
    gateway = session_gateway if session_gateway is not None else SESSION_GATEWAY

    def actor() -> str:
        session = gateway.require(PROSPECTING_OUTREACH_CAPABILITY)
        return str(session.get("session_id") or "authenticated-session")

    @mcp.tool(name="prospecting.outreach.plan")
    def prospecting_outreach_plan(
        company_id: str, channel: str, destination: str, body: str,
        campaign_id: str, authorization_basis: str, authorization_evidence_ref: str,
        subject: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a durable outreach draft. This operation never sends a message."""
        try:
            session_id = actor()
            plan = outreach.create_plan(
                company_id=company_id, channel=Channel(channel), destination=destination,
                subject=subject, body=body, campaign_id=campaign_id,
                authorization=ContactAuthorization(
                    basis=authorization_basis,
                    evidence_ref=authorization_evidence_ref,
                    reviewed_by=session_id,
                ),
            )
            return {"success": True, "plan_id": plan.plan_id, "status": plan.status.value}
        except Exception as exc:
            logger.warning("Prospecto outreach plan rejected: %s", type(exc).__name__)
            return {"success": False, "error_code": str(exc) if isinstance(exc, (ValueError, PermissionError)) else "outreach_plan_failed"}

    @mcp.tool(name="prospecting.outreach.approve")
    def prospecting_outreach_approve(plan_id: str) -> dict[str, Any]:
        """Approve one reviewed plan; approval is required before any dispatch."""
        try:
            plan = outreach.approve_plan(plan_id, approved_by=actor())
            return {"success": True, "plan_id": plan.plan_id, "status": plan.status.value}
        except Exception as exc:
            logger.warning("Prospecto outreach approval rejected: %s", type(exc).__name__)
            return {"success": False, "error_code": str(exc) if isinstance(exc, (ValueError, PermissionError)) else "outreach_approval_failed"}

    @mcp.tool(name="prospecting.outreach.dispatch")
    def prospecting_outreach_dispatch(plan_id: str, idempotency_key: str) -> dict[str, Any]:
        """Dispatch one approved plan through its configured channel relay."""
        try:
            actor()
            plan = outreach.dispatch(plan_id, idempotency_key=idempotency_key)
            return {"success": True, "plan_id": plan.plan_id, "status": plan.status.value}
        except Exception as exc:
            logger.warning("Prospecto outreach dispatch rejected: %s", type(exc).__name__)
            return {"success": False, "error_code": str(exc) if isinstance(exc, (ValueError, PermissionError, LookupError, RuntimeError)) else "outreach_dispatch_failed"}

    @mcp.tool(name="prospecting.outreach.history")
    def prospecting_outreach_history(plan_id: str) -> dict[str, Any]:
        """Read status and metadata-only audit events for one outreach plan."""
        try:
            actor()
            plan = outreach.get_plan(plan_id)
            return {
                "success": True,
                "plan_id": plan.plan_id,
                "status": plan.status.value,
                "events": outreach.list_events(plan_id),
            }
        except Exception as exc:
            logger.warning("Prospecto outreach history rejected: %s", type(exc).__name__)
            return {"success": False, "error_code": "outreach_history_unavailable"}

    @mcp.tool(name="prospecting.outreach.block")
    def prospecting_outreach_block(
        company_id: str, reason: str, channel: Optional[str] = None,
        destination: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record a terminal do-not-contact block for a company/channel or exact destination."""
        try:
            session_id = actor()
            outreach.block_contact(
                company_id=company_id,
                channel=Channel(channel) if channel is not None else None,
                destination=destination, reason=reason, recorded_by=session_id,
            )
            return {"success": True, "blocked": True}
        except Exception as exc:
            logger.warning("Prospecto outreach block rejected: %s", type(exc).__name__)
            return {"success": False, "error_code": str(exc) if isinstance(exc, ValueError) else "outreach_block_failed"}

    return PROSPECTING_OUTREACH_TOOLS


__all__ = ["register_prospecting_tools", "register_prospecting_outreach_tools", "PROSPECTING_CAPABILITY", "PROSPECTING_TOOLS", "PROSPECTING_OUTREACH_CAPABILITY", "PROSPECTING_OUTREACH_TOOLS"]
