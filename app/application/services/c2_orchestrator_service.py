# -*- coding: utf-8 -*-
"""C2 Orchestrator Service - Persistent session management for Soldier Mesh.

Implements Phase 1 of the Tactical Mesh protocol: a Command & Control layer
that manages authenticated Soldier sessions via SSH/WebSocket tunnels and
dispatches security audit payloads to them.

Architecture (Hexagonal):
    - This service lives in the Application layer.
    - Hardware/network transport is delegated to ``SecurityAuditAdapter``
      (edge adapter) via the ``TacticalCommandPort`` interface.
    - The ``KeepAliveProvider`` runs a background heartbeat loop that ensures
      Soldier tunnels never silently drop.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.application.ports.tactical_command_port import TacticalCommandPort
from app.application.services.device_orchestrator_service import DeviceOrchestratorService
from app.domain.models.soldier import SoldierStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_KEEPALIVE_INTERVAL_SEC = 30   # heartbeat cadence per Soldier
_MAX_MISSED_HEARTBEATS = 3     # mark offline after this many consecutive misses


class KeepAliveProvider:
    """
    Background heartbeat loop that pings each registered Soldier and marks
    it as OFFLINE (or triggers auto-repair) when heartbeats are missed.

    Args:
        orchestrator: ``DeviceOrchestratorService`` to query the registry
            and update Soldier statuses.
        command_port: Optional ``TacticalCommandPort`` used to send real
            heartbeat payloads.  When *None*, a stub ping is performed.
        interval: Seconds between heartbeat cycles (default 30).
        max_misses: Consecutive misses before marking a Soldier OFFLINE.
    """

    def __init__(
        self,
        orchestrator: DeviceOrchestratorService,
        command_port: Optional[TacticalCommandPort] = None,
        interval: float = _KEEPALIVE_INTERVAL_SEC,
        max_misses: int = _MAX_MISSED_HEARTBEATS,
    ) -> None:
        self._orchestrator = orchestrator
        self._command_port = command_port
        self._interval = interval
        self._max_misses = max_misses

        self._running = False
        self._thread: Optional[threading.Thread] = None
        # Per-Soldier miss counters
        self._miss_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the KeepAlive loop in a daemon thread (non-blocking)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="C2-KeepAlive"
        )
        self._thread.start()
        logger.info("💓 [C2-KeepAlive] Heartbeat loop iniciado (intervalo=%ds).", self._interval)

    def stop(self) -> None:
        """Signal the heartbeat loop to stop."""
        self._running = False
        logger.info("💓 [C2-KeepAlive] Heartbeat loop parando.")

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                logger.error("💓 [C2-KeepAlive] Erro no ciclo: %s", exc)
            time.sleep(self._interval)

    def _tick(self) -> None:
        """Ping all registered Soldiers and update their statuses."""
        soldiers = self._orchestrator.list_soldiers()
        for soldier in soldiers:
            alive = self._ping(soldier.soldier_id)
            if alive:
                self._miss_counts[soldier.soldier_id] = 0
                if soldier.status != SoldierStatus.ONLINE:
                    self._orchestrator.update_status(soldier.soldier_id, SoldierStatus.ONLINE)
                    logger.info(
                        "💓 [C2-KeepAlive] Soldado recuperado: %s", soldier.soldier_id
                    )
            else:
                misses = self._miss_counts.get(soldier.soldier_id, 0) + 1
                self._miss_counts[soldier.soldier_id] = misses
                logger.warning(
                    "💓 [C2-KeepAlive] Soldado '%s' sem resposta (%d/%d).",
                    soldier.soldier_id,
                    misses,
                    self._max_misses,
                )
                if misses >= self._max_misses:
                    self._orchestrator.update_status(
                        soldier.soldier_id, SoldierStatus.OFFLINE
                    )
                    logger.error(
                        "💓 [C2-KeepAlive] Soldado '%s' marcado OFFLINE.",
                        soldier.soldier_id,
                    )
                    self._trigger_auto_repair(soldier.soldier_id)

    def _ping(self, soldier_id: str) -> bool:
        """
        Send a heartbeat to the Soldier.

        Returns True if the Soldier is reachable, False otherwise.
        Uses ``TacticalCommandPort`` when available; stubs True otherwise
        (so tests / offline mode work without real network connectivity).
        """
        if self._command_port is None:
            return True  # no real transport — assume alive (safe default)

        try:
            result = self._command_port.execute_security_payload(
                node_id=soldier_id,
                tool="heartbeat",
                target_scope="localhost",
            )
            return bool(result.get("success"))
        except Exception as exc:
            logger.debug("💓 [C2-KeepAlive] Ping falhou para '%s': %s", soldier_id, exc)
            return False

    def _trigger_auto_repair(self, soldier_id: str) -> None:
        """Attempt to restart a failed Soldier connection via auto_fixer_logic."""
        try:
            from scripts.auto_fixer_logic import AutoFixer  # type: ignore

            fixer = AutoFixer()
            fixer.attempt_repair({"component": soldier_id, "reason": "heartbeat_failure"})
            logger.info("🔧 [C2-KeepAlive] Auto-repair disparado para '%s'.", soldier_id)
        except Exception as exc:
            logger.debug("🔧 [C2-KeepAlive] Auto-repair indisponível: %s", exc)


class C2OrchestratorService(TacticalCommandPort):
    """
    Command & Control orchestrator for the Soldier Mesh.

    Manages persistent Soldier sessions, dispatches security audit payloads,
    and delegates execution to a pluggable ``TacticalCommandPort`` adapter
    (default: ``SecurityAuditAdapter``).

    The ``KeepAliveProvider`` is automatically started when this service is
    instantiated so that Soldier tunnels are continuously monitored.

    Args:
        orchestrator: Soldier registry (``DeviceOrchestratorService``).
        audit_adapter: Optional ``TacticalCommandPort`` for actual tool
            execution.  When *None* the service operates in dry-run mode,
            returning placeholder results.
        keepalive_interval: Heartbeat interval in seconds.
    """

    def __init__(
        self,
        orchestrator: Optional[DeviceOrchestratorService] = None,
        audit_adapter: Optional[TacticalCommandPort] = None,
        keepalive_interval: float = _KEEPALIVE_INTERVAL_SEC,
    ) -> None:
        self._orchestrator = orchestrator or DeviceOrchestratorService()
        self._audit_adapter = audit_adapter
        self._keepalive = KeepAliveProvider(
            orchestrator=self._orchestrator,
            command_port=audit_adapter,
            interval=keepalive_interval,
        )
        self._keepalive.start()

    # ------------------------------------------------------------------
    # NexusComponent / TacticalCommandPort interface
    # ------------------------------------------------------------------

    def execute_security_payload(
        self,
        node_id: str,
        tool: str,
        target_scope: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch *tool* to Soldier *node_id* within *target_scope*.

        Args:
            node_id: Target Soldier identifier.
            tool: Security tool to invoke (e.g. ``"nmap"``, ``"arp_scan"``).
            target_scope: IP/CIDR scope authorised by the user.
            options: Additional tool-specific parameters.

        Returns:
            Dict with ``success``, ``node_id``, ``tool``, and ``result``.
        """
        soldier = self._orchestrator.get_soldier(node_id)
        if not soldier:
            logger.error("🎯 [C2] Soldado '%s' não registado.", node_id)
            return {
                "success": False,
                "node_id": node_id,
                "error": f"Soldier '{node_id}' not registered.",
            }

        if soldier.status == SoldierStatus.OFFLINE:
            logger.warning(
                "🎯 [C2] Soldado '%s' está OFFLINE; payload descartado.", node_id
            )
            return {
                "success": False,
                "node_id": node_id,
                "error": f"Soldier '{node_id}' is OFFLINE.",
            }

        logger.info(
            "🎯 [C2] Enviando payload: node=%s tool=%s scope=%s",
            node_id,
            tool,
            target_scope,
        )

        if self._audit_adapter is not None:
            return self._audit_adapter.execute_security_payload(
                node_id=node_id,
                tool=tool,
                target_scope=target_scope,
                options=options,
            )

        # Dry-run: no real adapter attached
        return {
            "success": True,
            "node_id": node_id,
            "tool": tool,
            "target_scope": target_scope,
            "result": {"dry_run": True},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_tactical_report(self) -> str:
        """
        Return a human-readable status line suitable for voice/chat output.

        Example output::

            Estado: 2 Soldado(s) em Modo SENTINELA. Localizações: [...]
        """
        soldiers = self._orchestrator.list_active_soldiers()
        if not soldiers:
            return "Estado: Nenhum Soldado activo registado."

        parts: List[str] = []
        for s in soldiers:
            loc = ""
            if s.lat is not None and s.lon is not None:
                loc = f"({s.lat:.4f}, {s.lon:.4f})"
            elif s.last_ip:
                loc = s.last_ip
            label = s.alias or s.soldier_id
            parts.append(f"{label}@{loc}" if loc else label)

        return (
            f"Estado: {len(soldiers)} Soldado(s) em Modo SENTINELA. "
            f"Localizações: [{', '.join(parts)}]."
        )

    def stop_keepalive(self) -> None:
        """Gracefully stop the KeepAlive background thread."""
        self._keepalive.stop()
