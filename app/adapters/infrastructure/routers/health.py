# -*- coding: utf-8 -*-
"""Health check router: /health endpoint with DB connectivity and RLS validation."""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from app.core.config import settings

logger = logging.getLogger(__name__)

RLS_PROTECTED_TABLES: List[str] = [
    "jarvis_capabilities",
    "evolution_rewards",
]


def create_health_router(db_adapter) -> APIRouter:
    """
    Create the health router.

    Args:
        db_adapter: SQLiteHistoryAdapter used to verify DB connectivity

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

    return router
