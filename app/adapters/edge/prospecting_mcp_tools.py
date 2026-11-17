"""Read-only MCP tools for Jarvis Prospecto's public CNPJ discovery."""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.nexus import nexus

logger = logging.getLogger(__name__)


def _resolve_adapter() -> Any | None:
    adapter = nexus.resolve("prospecting_adapter")
    if adapter is None or getattr(adapter, "__is_cloud_mock__", False):
        return None
    return adapter


def register_prospecting_tools(mcp: Any) -> tuple[str, ...]:
    """Register bounded CNPJ search and exact establishment lookup tools."""

    @mcp.tool(name="prospecting.companies.search")
    def prospecting_companies_search(
        uf: str,
        cnae_prefixes: list[str],
        municipalities: Optional[list[str]] = None,
        only_active: bool = True,
        include_secondary_cnae: bool = True,
        limit: int = 50,
        after_cnpj_basico: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search companies by Brazilian state, municipality and CNAE activity.

        Results are grouped by the 8-digit CNPJ root, with source provenance.
        This is discovery only: it does not contact companies.
        """
        try:
            adapter = _resolve_adapter()
            if adapter is None:
                return {
                    "success": False,
                    "error_code": "prospecting_adapter_unavailable",
                    "message": "Jarvis Prospecto adapter is unavailable.",
                }
            if not adapter.can_execute({"tool_id": "prospecting.companies.search", "scope": "local"}):
                return {
                    "success": False,
                    "error_code": "prospecting_store_unavailable",
                    "message": (
                        "CNPJ DuckDB store is not configured or is unavailable. "
                        f"Set {_store_env_name()} on the Jarvis runtime."
                    ),
                }
            return adapter.search_companies(
                uf=uf,
                cnae_prefixes=cnae_prefixes,
                municipalities=municipalities,
                only_active=only_active,
                include_secondary_cnae=include_secondary_cnae,
                limit=limit,
                after_cnpj_basico=after_cnpj_basico,
            )
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "invalid_arguments",
                "message": str(exc),
            }
        except Exception:
            logger.exception("Jarvis Prospecto company search failed")
            return {
                "success": False,
                "error_code": "prospecting_search_failed",
                "message": "The company search could not be completed.",
            }

    @mcp.tool(name="prospecting.companies.lookup")
    def prospecting_company_lookup(cnpj: str) -> dict[str, Any]:
        """Look up one exact 14-digit CNPJ establishment in the official dataset."""
        try:
            adapter = _resolve_adapter()
            if adapter is None:
                return {
                    "success": False,
                    "error_code": "prospecting_adapter_unavailable",
                    "message": "Jarvis Prospecto adapter is unavailable.",
                }
            if not adapter.can_execute({"tool_id": "prospecting.companies.lookup", "scope": "local"}):
                return {
                    "success": False,
                    "error_code": "prospecting_store_unavailable",
                    "message": (
                        "CNPJ DuckDB store is not configured or is unavailable. "
                        f"Set {_store_env_name()} on the Jarvis runtime."
                    ),
                }
            return adapter.lookup_company(cnpj)
        except ValueError as exc:
            return {
                "success": False,
                "error_code": "invalid_arguments",
                "message": str(exc),
            }
        except Exception:
            logger.exception("Jarvis Prospecto CNPJ lookup failed")
            return {
                "success": False,
                "error_code": "prospecting_lookup_failed",
                "message": "The CNPJ lookup could not be completed.",
            }

    return ("prospecting.companies.search", "prospecting.companies.lookup")


def _store_env_name() -> str:
    return "JARVIS_PROSPECTO_STORE_PATH"


__all__ = ["register_prospecting_tools"]
