"""Session-authorized MCP tools for private B2B/B2C/C2B demand requests."""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Optional
from uuid import NAMESPACE_URL, UUID, uuid5

from app.adapters.infrastructure.session_authorization import SESSION_GATEWAY
from app.adapters.infrastructure.prospecting.demand_store import (
    DemandNotFound,
    SQLiteDemandStore,
)
from app.domain.prospecting.demand import (
    DemandIntent,
    DemandRequest,
    MarketDirection,
    RequesterType,
)

logger = logging.getLogger(__name__)
DEMAND_CAPABILITY = "prospecting.demand.manage"
# Stable local tenant boundary for this single-owner Jarvis runtime.
LOCAL_TENANT_ID = uuid5(NAMESPACE_URL, "jarvis-xerife/local-owner")


def _store() -> SQLiteDemandStore:
    configured = os.getenv("JARVIS_PROSPECTO_DEMAND_DB", "").strip()
    database = Path(configured).expanduser() if configured else (
        Path.home() / ".local" / "share" / "jarvis" / "prospecto" / "demands.sqlite3"
    )
    return SQLiteDemandStore(database)


def register_prospecting_demand_tools(
    mcp: Any, *, store: Any = None, session_gateway: Any = None,
) -> tuple[str, ...]:
    """Register private demand creation and retrieval; no discovery or contact occurs."""
    repository = store if store is not None else _store()
    gateway = session_gateway if session_gateway is not None else SESSION_GATEWAY

    def actor() -> str:
        session = gateway.require(DEMAND_CAPABILITY)
        return str(session.get("session_id") or "local-owner")

    @mcp.tool(name="prospecting.demands.create")
    def prospecting_demand_create(
        requester_type: str,
        direction: str,
        intent: str,
        title: str,
        description: str,
        categories: list[str],
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: str = "BR",
        remote_allowed: bool = False,
        radius_km: Optional[int] = None,
        profile_reference: Optional[str] = None,
        consent_to_share_profile: bool = False,
        consent_scope: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a private search request. CV sharing is opt-in and request-scoped."""
        try:
            requester_id = actor()
            consent_at = None
            if consent_to_share_profile:
                from datetime import datetime, timezone
                consent_at = datetime.now(timezone.utc)
            demand = DemandRequest(
                tenant_id=LOCAL_TENANT_ID,
                requester_id=requester_id,
                requester_type=RequesterType(requester_type),
                direction=MarketDirection(direction),
                intent=DemandIntent(intent),
                title=title,
                description=description,
                categories=tuple(categories),
                city=city,
                state=state,
                country=country,
                remote_allowed=remote_allowed,
                radius_km=radius_km,
                profile_reference=profile_reference,
                consent_to_share_profile=consent_to_share_profile,
                consent_recorded_at=consent_at,
                consent_scope=consent_scope,
            )
            repository.create(demand)
            return {
                "success": True,
                "demand_id": str(demand.demand_id),
                "direction": demand.direction.value,
                "intent": demand.intent.value,
                "status": demand.status.value,
                "profile_sharing_enabled": demand.consent_to_share_profile,
            }
        except Exception as exc:
            logger.warning("Prospecto demand creation rejected: %s", type(exc).__name__)
            return {
                "success": False,
                "error_code": str(exc) if isinstance(exc, ValueError) else "demand_creation_failed",
            }

    @mcp.tool(name="prospecting.demands.get")
    def prospecting_demand_get(demand_id: str) -> dict[str, Any]:
        """Retrieve one private demand belonging to the authenticated local tenant."""
        try:
            actor()
            demand = repository.get(UUID(demand_id), tenant_id=LOCAL_TENANT_ID)
            return {"success": True, "demand": demand.model_dump(mode="json")}
        except (ValueError, DemandNotFound):
            return {"success": False, "error_code": "demand_not_found"}
        except Exception as exc:
            logger.warning("Prospecto demand retrieval rejected: %s", type(exc).__name__)
            return {"success": False, "error_code": "demand_retrieval_failed"}

    @mcp.tool(name="prospecting.demands.list")
    def prospecting_demand_list(limit: int = 50) -> dict[str, Any]:
        """List private demands owned by the authenticated local session."""
        try:
            requester_id = actor()
            demands = repository.list_for_requester(
                requester_id, tenant_id=LOCAL_TENANT_ID, limit=limit,
            )
            return {
                "success": True,
                "demands": [demand.model_dump(mode="json") for demand in demands],
                "count": len(demands),
            }
        except ValueError as exc:
            return {"success": False, "error_code": str(exc)}
        except Exception as exc:
            logger.warning("Prospecto demand listing rejected: %s", type(exc).__name__)
            return {"success": False, "error_code": "demand_listing_failed"}

    return (
        "prospecting.demands.create",
        "prospecting.demands.get",
        "prospecting.demands.list",
    )


__all__ = ["DEMAND_CAPABILITY", "register_prospecting_demand_tools"]
