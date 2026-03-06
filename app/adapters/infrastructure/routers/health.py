# -*- coding: utf-8 -*-
"""Health check router: /health and /v1/health/detail endpoints."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from app.core.config import settings

logger = logging.getLogger(__name__)

RLS_PROTECTED_TABLES: List[str] = [
    "jarvis_capabilities",
    "evolution_rewards",
]


def create_health_router(db_adapter, get_current_user=None) -> APIRouter:
    """
    Create the health router.

    Args:
        db_adapter: SQLiteHistoryAdapter used to verify DB connectivity
        get_current_user: Optional auth dependency for protected endpoints.

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.get("/health")
    async def health_check() -> Dict[str, Any]:
        """
        Health check endpoint validating database connectivity and RLS settings.

        Returns:
            JSON with status, database info, and security (RLS) status
        """
        response: Dict[str, Any] = {
            "status": "healthy",
            "version": "1.0.0",
            "database": {"connected": False, "type": "unknown"},
            "security": {
                "rls_enabled": False,
                "tables_checked": [],
                "tables_without_rls": [],
            },
        }

        try:
            if not settings.database_url or settings.database_url.startswith("sqlite://"):
                response["database"]["connected"] = True
                response["database"]["type"] = "sqlite"
                response["security"]["rls_enabled"] = "n/a"
                response["security"]["note"] = "SQLite does not support Row Level Security"
                return response

            if "postgresql" in settings.database_url or "postgres" in settings.database_url:
                response["database"]["type"] = "postgresql"
                from sqlmodel import Session, text

                with Session(db_adapter.engine) as session:
                    session.exec(text("SELECT 1"))
                    response["database"]["connected"] = True

                    table_list = ", ".join(f"'{t}'" for t in RLS_PROTECTED_TABLES)
                    rls_query = text(
                        f"""
                        SELECT schemaname, tablename, rowsecurity
                        FROM pg_tables
                        WHERE schemaname = 'public'
                        AND tablename IN ({table_list})
                        ORDER BY tablename
                        """
                    )
                    results = session.exec(rls_query).fetchall()

                    tables_with_rls: List[str] = []
                    tables_without_rls: List[str] = []

                    for row in results:
                        table_name = row[1]
                        rls_enabled = row[2]
                        response["security"]["tables_checked"].append(table_name)
                        (tables_with_rls if rls_enabled else tables_without_rls).append(table_name)

                    response["security"]["tables_without_rls"] = tables_without_rls

                    if not tables_without_rls and tables_with_rls:
                        response["security"]["rls_enabled"] = True
                    elif tables_without_rls:
                        response["security"]["rls_enabled"] = False
                        response["status"] = "degraded"
                        response["security"]["warning"] = (
                            f"Row Level Security is NOT enabled on: {', '.join(tables_without_rls)}"
                        )
                    else:
                        response["security"]["rls_enabled"] = "unknown"
                        response["security"]["note"] = "No tables found in database"

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            response["status"] = "unhealthy"
            response["database"]["connected"] = False
            response["error"] = str(e)

        return response

    # ------------------------------------------------------------------
    # /v1/health/detail — detailed health endpoint (Etapa 11)
    # ------------------------------------------------------------------

    _auth_deps: List[Any] = [Depends(get_current_user)] if get_current_user else []

    @router.get("/v1/health/detail", dependencies=_auth_deps)
    async def health_detail() -> Dict[str, Any]:
        """Detailed health endpoint covering all JARVIS subsystems.

        Each section uses graceful fallback: if the component is unavailable,
        the section contains ``{"available": false}`` and the endpoint still
        returns HTTP 200.
        """
        from app.core.nexus import nexus

        result: Dict[str, Any] = {}

        # Nexus section -------------------------------------------------------
        try:
            loaded_ids = nexus.list_loaded_ids()
            result["nexus"] = {"available": True, "loaded_components": loaded_ids}
        except Exception as exc:
            logger.warning("[health/detail] nexus: %s", exc)
            result["nexus"] = {"available": False, "error": str(exc)}

        # Evolution section ---------------------------------------------------
        try:
            from app.application.services.auto_evolutionV2 import AutoEvolutionServiceV2
            metrics = AutoEvolutionServiceV2().get_success_metrics()
            result["evolution"] = {
                "available": True,
                "evolution_rate": metrics.get("evolution_rate", 0.0),
                "missions_completed": metrics.get("missions_completed", 0),
                "total_missions": metrics.get("total_missions", 0),
            }
        except Exception as exc:
            logger.warning("[health/detail] evolution: %s", exc)
            result["evolution"] = {"available": False, "error": str(exc)}

        # MetaReflection section ----------------------------------------------
        try:
            from app.application.services.meta_reflection import MetaReflection
            reflection = MetaReflection.load_latest()
            if reflection:
                result["meta_reflection"] = {
                    "available": True,
                    "fragile_modules": reflection.get("fragile_modules", []),
                    "rejection_patterns": reflection.get("rejection_patterns", {}),
                }
            else:
                result["meta_reflection"] = {"available": True, "reflection": None}
        except Exception as exc:
            logger.warning("[health/detail] meta_reflection: %s", exc)
            result["meta_reflection"] = {"available": False, "error": str(exc)}

        # FineTune section ----------------------------------------------------
        try:
            ft = nexus.resolve("finetune_trigger_service")
            last_trigger: Optional[Any] = None
            if ft is not None and hasattr(ft, "last_trigger_at"):
                last_trigger = ft.last_trigger_at
            result["finetune"] = {"available": ft is not None, "last_trigger": last_trigger}
        except Exception as exc:
            logger.warning("[health/detail] finetune: %s", exc)
            result["finetune"] = {"available": False, "error": str(exc)}

        # Gatekeeper section --------------------------------------------------
        try:
            from pathlib import Path as _Path
            import json as _json
            rejections_file = _Path("data/gatekeeper_rejections.jsonl")
            total_rejections = 0
            rejections_7d = 0
            if rejections_file.exists():
                from datetime import datetime as _dt, timezone as _tz, timedelta as _td
                cutoff = (_dt.now(tz=_tz.utc) - _td(days=7)).timestamp()
                for line in rejections_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = _json.loads(line)
                        total_rejections += 1
                        ts = entry.get("timestamp")
                        if ts is not None and float(ts) >= cutoff:
                            rejections_7d += 1
                    except Exception:
                        pass
            result["gatekeeper"] = {
                "available": True,
                "total_rejections": total_rejections,
                "rejections_last_7d": rejections_7d,
            }
        except Exception as exc:
            logger.warning("[health/detail] gatekeeper: %s", exc)
            result["gatekeeper"] = {"available": False, "error": str(exc)}

        # Resources section ---------------------------------------------------
        try:
            resource_monitor = nexus.resolve("overwatch_resource_monitor")
            if resource_monitor is not None and hasattr(resource_monitor, "get_resource_trends"):
                trends = resource_monitor.get_resource_trends()
                result["resources"] = {"available": True, **trends}
            else:
                result["resources"] = {"available": False, "error": "not_loaded"}
        except Exception as exc:
            logger.warning("[health/detail] resources: %s", exc)
            result["resources"] = {"available": False, "error": str(exc)}

        return result

    return router
