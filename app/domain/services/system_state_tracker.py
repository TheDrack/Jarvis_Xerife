# -*- coding: utf-8 -*-
"""SystemStateTracker — Consciência de estado do sistema para tomada de decisões.

Captura snapshots de CPU, RAM, filas e capabilities ativas antes de cada
decisão. Persiste snapshots em formato .jrvs com hash de integridade e
integra com ThoughtLogService para correlação de estados com pensamentos.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_SNAPSHOTS_DIR = Path("data/system_snapshots")
_MAX_HISTORY = 100  # máximo de snapshots retidos na memória


class SystemStateTracker(NexusComponent):
    """Rastreia e persiste o estado do sistema para cada decisão tomada.

    Métodos principais:
        capture_snapshot()    — captura CPU, RAM, filas e capabilities ativas.
        get_health_metrics()  — calcula metabolic_rate e score geral de saúde.
        get_recent_snapshots() — retorna os últimos N snapshots capturados.
    """

    def __init__(self) -> None:
        self._history: List[Dict[str, Any]] = []
        _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent.

        Campos aceitos em *context*:
            action (str) — "snapshot" | "health" | "history". Padrão: "snapshot".
            decision_id (str) — identificador opcional da decisão em curso.
            limit (int) — número de snapshots a retornar quando action="history".

        Returns:
            Dicionário com o resultado da ação solicitada.
        """
        ctx = context or {}
        action = ctx.get("action", "snapshot")

        if action == "health":
            return {"success": True, "health": self.get_health_metrics()}
        if action == "history":
            limit = int(ctx.get("limit", 10))
            return {"success": True, "snapshots": self.get_recent_snapshots(limit)}

        # default: snapshot
        snapshot = self.capture_snapshot(decision_id=ctx.get("decision_id"))
        return {"success": True, "snapshot": snapshot}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture_snapshot(self, decision_id: Optional[str] = None) -> Dict[str, Any]:
        """Captura o estado atual do sistema e persiste em disco.

        Args:
            decision_id: Identificador opcional da decisão que motivou o snapshot.

        Returns:
            Dicionário com os dados do snapshot capturado.
        """
        snapshot = self._build_snapshot(decision_id)
        self._store_snapshot(snapshot)
        return snapshot

    def get_health_metrics(self) -> Dict[str, Any]:
        """Calcula métricas de saúde do sistema baseadas nos snapshots recentes.

        Returns:
            Dicionário com ``metabolic_rate``, ``cpu_avg``, ``ram_avg`` e ``status``.
        """
        recent = self.get_recent_snapshots(limit=10)
        if not recent:
            return {"metabolic_rate": 1.0, "cpu_avg": 0.0, "ram_avg": 0.0, "status": "unknown"}

        cpu_values = [s.get("cpu_percent", 0.0) for s in recent]
        ram_values = [s.get("ram_percent", 0.0) for s in recent]
        cpu_avg = sum(cpu_values) / len(cpu_values)
        ram_avg = sum(ram_values) / len(ram_values)

        # metabolic_rate: 1.0 = saudável, >1.5 = sob pressão, <0.5 = ocioso
        load_factor = (cpu_avg + ram_avg) / 200.0  # normalizado 0→1
        metabolic_rate = max(0.1, round(0.5 + load_factor * 2.0, 3))

        if load_factor > 0.8:
            status = "critical"
        elif load_factor > 0.6:
            status = "warning"
        else:
            status = "healthy"

        return {
            "metabolic_rate": metabolic_rate,
            "cpu_avg": round(cpu_avg, 2),
            "ram_avg": round(ram_avg, 2),
            "status": status,
        }

    def get_recent_snapshots(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna os N snapshots mais recentes mantidos em memória.

        Args:
            limit: Número máximo de snapshots a retornar.

        Returns:
            Lista de dicionários de snapshot, do mais recente ao mais antigo.
        """
        return list(reversed(self._history[-limit:]))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_snapshot(self, decision_id: Optional[str]) -> Dict[str, Any]:
        """Monta o dicionário de snapshot lendo métricas do sistema."""
        cpu_percent, ram_percent, ram_used_mb = self._read_system_metrics()

        snapshot: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "cpu_percent": cpu_percent,
            "ram_percent": ram_percent,
            "ram_used_mb": ram_used_mb,
            "active_capabilities": self._get_active_capabilities(),
            "queue_depth": self._get_queue_depth(),
            "decision_id": decision_id,
        }
        snapshot["integrity_hash"] = self._compute_hash(snapshot)
        return snapshot

    def _read_system_metrics(self):
        """Lê CPU e RAM via psutil se disponível, senão retorna zeros."""
        try:
            import psutil  # type: ignore

            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            return cpu, mem.percent, round(mem.used / (1024 * 1024), 2)
        except Exception:
            return 0.0, 0.0, 0.0

    def _get_active_capabilities(self) -> List[str]:
        """Retorna IDs de componentes carregados no Nexus."""
        try:
            from app.core.nexus import nexus

            return nexus.list_loaded_ids()
        except Exception:
            return []

    def _get_queue_depth(self) -> int:
        """Tenta ler o tamanho da fila de tarefas ativas (best-effort)."""
        try:
            from app.core.nexus import nexus

            task_runner = nexus.resolve("task_runner")
            if hasattr(task_runner, "queue_depth"):
                return int(task_runner.queue_depth())
        except Exception:
            pass
        return 0

    @staticmethod
    def _compute_hash(snapshot: Dict[str, Any]) -> str:
        """Gera um hash SHA-256 dos campos principais para garantir integridade."""
        fields = {k: v for k, v in snapshot.items() if k != "integrity_hash"}
        serialized = json.dumps(fields, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()[:32]

    def _store_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Persiste o snapshot em memória e em arquivo .jrvs no disco."""
        self._history.append(snapshot)
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]

        try:
            ts = snapshot.get("epoch", time.time())
            fname = _SNAPSHOTS_DIR / f"snapshot_{int(ts)}.jrvs"
            with open(fname, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.debug("Falha ao persistir snapshot: %s", exc)
