# -*- coding: utf-8 -*-
"""CostTrackerAdapter — auditoria de custos de chamadas LLM.

Registra por chamada: modelo, task_type, tokens de prompt e completion,
custo estimado em USD (via tabela de preços em config/llm_fleet.json),
success e timestamp.

Persiste em uma tabela SQLite ``llm_cost_log`` usando o mesmo engine do
SQLiteHistoryAdapter.

Expõe:
    log(...)                → registra uma chamada
    get_cost_summary(days)  → custo total, por modelo e por task_type
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_FLEET_CONFIG = Path("config/llm_fleet.json")

# Preços padrão por 1k tokens (USD) caso llm_fleet.json não tenha entrada
_DEFAULT_PRICE_PER_1K_INPUT = 0.0001
_DEFAULT_PRICE_PER_1K_OUTPUT = 0.0002


def _load_price_table() -> Dict[str, Dict[str, float]]:
    """Lê a tabela de preços de config/llm_fleet.json."""
    if not _FLEET_CONFIG.exists():
        return {}
    try:
        data = json.loads(_FLEET_CONFIG.read_text(encoding="utf-8"))
        table: Dict[str, Dict[str, float]] = {}
        models = data if isinstance(data, list) else data.get("models", [])
        for m in models:
            name = m.get("model") or m.get("name", "")
            if name:
                table[name] = {
                    "input_per_1k": float(m.get("price_input_per_1k", _DEFAULT_PRICE_PER_1K_INPUT)),
                    "output_per_1k": float(m.get("price_output_per_1k", _DEFAULT_PRICE_PER_1K_OUTPUT)),
                }
        return table
    except Exception as exc:
        logger.debug("[CostTracker] Falha ao carregar price table: %s", exc)
        return {}


class CostTrackerAdapter(NexusComponent):
    """Rastreador de custos de chamadas LLM.

    Integra ao ai_gateway.py: após cada resposta LLM, chamar ``log(...)``.
    """

    def __init__(self, db_path: str = "jarvis.db", database_url: Optional[str] = None) -> None:
        self._db_path = db_path
        self._database_url = database_url or os.getenv("DATABASE_URL")
        self._engine: Any = None
        self._price_table: Dict[str, Dict[str, float]] = {}

    # ------------------------------------------------------------------
    # NexusComponent contract
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa ação de log ou summary conforme campo ``action``."""
        ctx = context or {}
        action = ctx.get("action", "summary")
        if action == "log":
            self.log(
                model=ctx.get("model", "unknown"),
                task_type=ctx.get("task_type", "unknown"),
                prompt_tokens=int(ctx.get("prompt_tokens", 0)),
                completion_tokens=int(ctx.get("completion_tokens", 0)),
                success=bool(ctx.get("success", True)),
            )
            return {"success": True, "action": "logged"}
        days = int(ctx.get("period_days", 7))
        return {"success": True, "summary": self.get_cost_summary(days)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        model: str,
        task_type: str,
        prompt_tokens: int,
        completion_tokens: int,
        success: bool = True,
    ) -> None:
        """Registra uma chamada LLM na tabela llm_cost_log."""
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)
        try:
            from sqlalchemy import text as sa_text  # lazy import
            engine = self._get_engine()
            if engine is None:
                return
            insert_sql = sa_text(
                "INSERT INTO llm_cost_log "
                "(model, task_type, prompt_tokens, completion_tokens, estimated_cost_usd, success, timestamp) "
                "VALUES (:model, :task_type, :prompt_tokens, :completion_tokens, "
                ":estimated_cost_usd, :success, :timestamp)"
            )
            with engine.connect() as conn:
                conn.execute(
                    insert_sql,
                    {
                        "model": model,
                        "task_type": task_type,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "estimated_cost_usd": cost,
                        "success": int(success),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                conn.commit()
        except Exception as exc:
            logger.debug("[CostTracker] Falha ao registrar chamada: %s", exc)

    def get_cost_summary(self, period_days: int = 7) -> Dict[str, Any]:
        """Retorna custo total, por modelo e por task_type no período."""
        try:
            from sqlalchemy import text as sa_text  # lazy import
            engine = self._get_engine()
            if engine is None:
                return {"total": 0.0, "by_model": {}, "by_task_type": {}}
            since = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
            select_sql = sa_text(
                "SELECT model, task_type, prompt_tokens, completion_tokens, estimated_cost_usd "
                "FROM llm_cost_log WHERE timestamp >= :since"
            )
            with engine.connect() as conn:
                rows = list(conn.execute(select_sql, {"since": since}))
        except Exception as exc:
            logger.debug("[CostTracker] Falha ao consultar resumo: %s", exc)
            return {"total": 0.0, "by_model": {}, "by_task_type": {}}

        total = 0.0
        by_model: Dict[str, float] = {}
        by_task: Dict[str, float] = {}
        for row in rows:
            cost = float(row[4]) if row[4] else 0.0
            model = str(row[0])
            task = str(row[1])
            total += cost
            by_model[model] = by_model.get(model, 0.0) + cost
            by_task[task] = by_task.get(task, 0.0) + cost

        return {
            "total": round(total, 6),
            "by_model": {k: round(v, 6) for k, v in by_model.items()},
            "by_task_type": {k: round(v, 6) for k, v in by_task.items()},
            "period_days": period_days,
        }

    def get_median_cost(self, task_type: str) -> float:
        """Retorna o custo mediano para o task_type no histórico completo."""
        try:
            from sqlalchemy import text as sa_text  # lazy import
            engine = self._get_engine()
            if engine is None:
                return 0.0
            select_sql = sa_text(
                "SELECT estimated_cost_usd FROM llm_cost_log WHERE task_type = :task_type"
            )
            with engine.connect() as conn:
                rows = list(conn.execute(select_sql, {"task_type": task_type}))
            costs = sorted(float(r[0]) for r in rows if r[0] is not None)
            if not costs:
                return 0.0
            mid = len(costs) // 2
            return costs[mid] if len(costs) % 2 else (costs[mid - 1] + costs[mid]) / 2
        except Exception as exc:
            logger.debug("[CostTracker] Falha ao calcular mediana: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        if not self._price_table:
            self._price_table = _load_price_table()
        prices = self._price_table.get(model, {})
        p_in = prices.get("input_per_1k", _DEFAULT_PRICE_PER_1K_INPUT)
        p_out = prices.get("output_per_1k", _DEFAULT_PRICE_PER_1K_OUTPUT)
        return (prompt_tokens * p_in + completion_tokens * p_out) / 1000.0

    def _get_engine(self) -> Any:
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    def _create_engine(self) -> Any:
        try:
            from sqlalchemy import create_engine, text  # lazy
            db_url = self._database_url or f"sqlite:///{self._db_path}"
            eng = create_engine(db_url, pool_pre_ping=True)
            # Create table if not exists
            with eng.connect() as conn:
                conn.execute(text(_CREATE_TABLE_SQL))
                conn.commit()
            return eng
        except Exception as exc:
            logger.warning("[CostTracker] Falha ao criar engine: %s", exc)
            return None


# ---------------------------------------------------------------------------
# SQL DDL
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS llm_cost_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    task_type TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    success INTEGER DEFAULT 1,
    timestamp TEXT NOT NULL
)
"""
