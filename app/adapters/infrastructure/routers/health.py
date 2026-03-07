
# -*- coding: utf-8 -*-
"""Health check router: /health, /v1/health/detail e /warmup endpoints."""
import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from app.core.config import settings
from app.core.nexus import nexus

logger = logging.getLogger(__name__)

# Tabelas protegidas por RLS (Row Level Security) no PostgreSQL
RLS_PROTECTED_TABLES: List[str] = [
    "jarvis_capabilities",
    "evolution_rewards",
    "users",
    "voice_profiles",
]


def create_health_router(db_adapter, get_current_user=None) -> APIRouter:
    """
    Cria o roteador de health check com endpoints de diagnóstico.
    
    Args:
        db_adapter: SQLiteHistoryAdapter usado para verificar conectividade do DB
        get_current_user: Dependência de autenticação opcional para endpoints protegidos.
    
    Returns:
        APIRouter configurado com os endpoints /health, /v1/health/detail e /warmup.
    """
    router = APIRouter()

    # ------------------------------------------------------------------
    # /health — Health check básico (público, usado pelo Render)
    # ------------------------------------------------------------------
    @router.get("/health")
    async def health_check() -> Dict[str, Any]:
        """
        Health check endpoint validando conectividade do banco e status do Nexus.
        Retorna HTTP 200 mesmo em modo degradado para evitar restarts desnecessários.
        
        Returns:
            JSON com status, informações do banco e status de segurança (RLS).
        """
        start_ts = time.monotonic()
        response: Dict[str, Any] = {
            "status": "healthy",
            "version": settings.version,
            "database": {"connected": False, "type": "unknown"},
            "security": {
                "rls_enabled": False,
                "tables_checked": [],
                "tables_without_rls": [],
            },
            "response_time_ms": 0.0,
        }

        try:
            # Verifica tipo de banco
            if not settings.database_url or settings.database_url.startswith("sqlite://"):
                response["database"]["connected"] = True
                response["database"]["type"] = "sqlite"
                response["security"]["rls_enabled"] = "n/a"
                response["security"]["note"] = "SQLite não suporta Row Level Security"
            elif "postgresql" in settings.database_url or "postgres" in settings.database_url:
                response["database"]["type"] = "postgresql"
                from sqlmodel import Session, text

                with Session(db_adapter.engine) as session:
                    session.exec(text("SELECT 1"))
                    response["database"]["connected"] = True

                # Verifica RLS nas tabelas protegidas
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
                with Session(db_adapter.engine) as session:
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
                            f"RLS NÃO habilitado em: {', '.join(tables_without_rls)}"
                        )
                    else:
                        response["security"]["rls_enabled"] = "unknown"
                        response["security"]["note"] = "Nenhuma tabela encontrada no banco"

        except Exception as e:
            logger.error(f"Health check falhou: {e}", exc_info=True)
            response["status"] = "degraded"
            response["database"]["connected"] = False
            response["error"] = str(e)

        response["response_time_ms"] = round((time.monotonic() - start_ts) * 1000, 2)
        return response

    # ------------------------------------------------------------------
    # /v1/health/detail — Health check detalhado (protegido por autenticação)
    # ------------------------------------------------------------------
    _auth_deps: List[Any] = [Depends(get_current_user)] if get_current_user else []

    @router.get("/v1/health/detail", dependencies=_auth_deps)
    async def health_detail() -> Dict[str, Any]:
        """
        Endpoint de health detalhado cobrindo todos os subsistemas do JARVIS.
        Cada seção usa fallback gracioso: se o componente não está disponível,
        a seção contém ``{"available": false}`` e o endpoint ainda retorna HTTP 200.
        
        Seções incluídas:
        - nexus: Componentes carregados no container DI
        - evolution: Status da auto-evolução (taxa, missões completas)
        - meta_reflection: Módulos frágeis e padrões de rejeição do Gatekeeper
        - finetune: Último disparo de fine-tuning
        - gatekeeper: Total de rejeições e rejeições nos últimos 7 dias
        - resources: Tendências de CPU e RAM (via OverwatchDaemon)
        
        Returns:
            Dicionário com o status de cada subsistema.
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

    # ------------------------------------------------------------------
    # /warmup — Endpoint para prevenir spin-down no Render
    # ------------------------------------------------------------------
    @router.get("/warmup")
    async def warmup() -> Dict[str, Any]:
        """
        Endpoint de warmup para prevenir spin-down no Render.
        
        O Render pode encerrar instâncias inativas após ~15 minutos.
        Chame este endpoint a cada 10-14 minutos via cron externo
        (ex: cron-job.org, UptimeRobot, GitHub Actions scheduled)
        para manter a instância aquecida.
        
        Este endpoint:
        1. Resolve componentes críticos do Nexus (mantém cache quente)
        2. Verifica conectividade do banco
        3. Retorna tempo de resposta para monitoramento
        
        Returns:
            JSON com status, componentes resolvidos e tempo de resposta.
        """
        start_ts = time.monotonic()
        result: Dict[str, Any] = {
            "status": "warm",
            "timestamp": time.time(),
            "response_time_ms": 0.0,
            "components_resolved": [],
            "database_connected": False,
        }

        # Resolve componentes críticos (mantém cache do Nexus quente)
        critical_components = [
            "assistant_service",
            "command_interpreter",
            "intent_processor",
            "sqlite_history_adapter",
        ]

        for comp_id in critical_components:
            try:
                comp = nexus.resolve(comp_id)
                if comp is not None:
                    result["components_resolved"].append(comp_id)
            except Exception as exc:
                logger.debug(f"[warmup] {comp_id}: {exc}")

        # Verifica conectividade do banco
        try:
            from sqlmodel import Session, text

            with Session(db_adapter.engine) as session:
                session.exec(text("SELECT 1"))
                result["database_connected"] = True
        except Exception as exc:
            logger.debug(f"[warmup] database: {exc}")

        result["response_time_ms"] = round((time.monotonic() - start_ts) * 1000, 2)

        # Log para auditoria (opcional)
        logger.info(
            "[warmup] status=%s components=%d db=%s response_time=%.2fms",
            result["status"],
            len(result["components_resolved"]),
            result["database_connected"],
            result["response_time_ms"],
        )

        return result

    return router