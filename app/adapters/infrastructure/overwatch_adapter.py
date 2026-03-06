# -*- coding: utf-8 -*-
"""Overwatch Daemon - JARVIS Proactive Core (Hexagonal Architecture).

A background process that runs independently of the main command loop and
monitors the system, the user's context file, and resource usage, triggering
proactive notifications and suggestions.

Monitoring responsibilities:
- CPU / RAM usage: warns via voice / notification when consistently high.
- ``data/context.json`` changes: reacts to context updates.
- User inactivity (30 min): uses VisionAdapter to check if the user is present;
  if so, suggests a pending task from the calendar.
- Tactical Perimeter (Phase 3): detects unauthorised MACs and ARP-spoofing
  attacks reported by Soldiers; blocks the attacker, notifies the Commander,
  and stores the forensic trace in VectorMemoryAdapter.
- Predictive alerts (MELHORIA 6): janela deslizante de 10 leituras; dispara
  notificação preventiva se tendência de crescimento ultrapassar limiares.

All proactive actions are logged with the ``[PROACTIVE_CORE]`` prefix.

Usage (embedded in main.py):
    from app.adapters.infrastructure.overwatch_adapter import OverwatchDaemon
    daemon = OverwatchDaemon()
    daemon.start()  # non-blocking, runs in a daemon thread
"""

import collections
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set

from app.core.nexus import nexus, NexusComponent
from app.utils.document_store import document_store
from app.adapters.infrastructure.overwatch_resource_monitor import ResourceMonitor
from app.adapters.infrastructure.overwatch_perimeter import PerimeterMonitor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_POLL_INTERVAL_SEC = 10          # main loop tick
_CPU_CHECK_EVERY = 6             # ticks (every ~60 s)
_CPU_HIGH_THRESHOLD = 85.0       # %
_RAM_HIGH_THRESHOLD = 85.0       # %
_INACTIVITY_TIMEOUT_SEC = 1800   # 30 minutes
_CONTEXT_FILE = Path("data/context.jrvs")
_PERIMETER_CHECK_EVERY = 3       # ticks (every ~30 s)
_OVERWATCH_COMPILE_INTERVAL_SEC = float(
    os.getenv("OVERWATCH_COMPILE_INTERVAL_SEC", "600")
)  # 10 minutes

# Predictive thresholds (MELHORIA 6)
_PREDICTIVE_CPU_THRESHOLD = 80.0  # %
_PREDICTIVE_RAM_THRESHOLD = 85.0  # %
_SLIDING_WINDOW_SIZE = 10


class OverwatchDaemon(ResourceMonitor, PerimeterMonitor):
    """
    Proactive monitoring daemon for JARVIS.

    Implements NexusComponent to allow resolution via nexus.resolve("overwatch_daemon").

    Args:
        poll_interval: Main loop tick in seconds (default: 10).
        cpu_threshold: CPU % that triggers a high-usage warning (default: 85).
        ram_threshold: RAM % that triggers a high-usage warning (default: 85).
        inactivity_timeout: Seconds of inactivity before the user-presence check (default: 1800).
    """

    def __init__(
        self,
        poll_interval: float = _POLL_INTERVAL_SEC,
        cpu_threshold: float = _CPU_HIGH_THRESHOLD,
        ram_threshold: float = _RAM_HIGH_THRESHOLD,
        inactivity_timeout: float = _INACTIVITY_TIMEOUT_SEC,
        authorized_macs: Optional[Set[str]] = None,
    ) -> None:
        self._poll_interval = poll_interval
        self._cpu_threshold = cpu_threshold
        self._ram_threshold = ram_threshold
        self._inactivity_timeout = inactivity_timeout

        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._last_activity_ts: float = time.monotonic()
        self._context_mtime: Optional[float] = None
        self._tick_count: int = 0
        self._last_compile_ts: float = 0.0  # timestamp of last compile_all run

        # Tactical Perimeter state
        self._authorized_macs: Set[str] = {m.upper() for m in (authorized_macs or set())}
        self._blocked_macs: Set[str] = set()

        # Predictive monitoring — sliding windows (MELHORIA 6)
        self._cpu_history: Deque[float] = collections.deque(maxlen=_SLIDING_WINDOW_SIZE)
        self._ram_history: Deque[float] = collections.deque(maxlen=_SLIDING_WINDOW_SIZE)

    # ------------------------------------------------------------------
    # NexusComponent contract
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Implementação do contrato NexusComponent."""
        ctx = context or {}
        action = ctx.get("action", "status")
        if action == "notify_activity":
            self.notify_activity()
            return {"success": True, "action": "activity_notified"}
        return {"success": True, "running": self._running, "tick": self._tick_count}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the daemon in a background daemon thread (non-blocking)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="OverwatchDaemon"
        )
        self._thread.start()
        logger.info("[PROACTIVE_CORE] OverwatchDaemon iniciado.")

    def stop(self) -> None:
        """Signal the daemon to stop at the next tick."""
        self._running = False
        logger.info("[PROACTIVE_CORE] OverwatchDaemon parando…")

    def notify_activity(self) -> None:
        """Call this whenever the user sends a command to reset the inactivity timer."""
        self._last_activity_ts = time.monotonic()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        logger.info("[PROACTIVE_CORE] Loop principal iniciado.")
        while self._running:
            self._tick_count += 1
            try:
                self._check_resources()
                self._check_context_file()
                self._check_inactivity()
                self._check_tactical_perimeter()
                self._check_jrvs_compile()
            except Exception as exc:
                logger.error("[PROACTIVE_CORE] Erro no loop principal: %s", exc)
            time.sleep(self._poll_interval)
        logger.info("[PROACTIVE_CORE] Loop principal encerrado.")

    # ------------------------------------------------------------------
    # Monitoring tasks
    # ------------------------------------------------------------------

    def _check_context_file(self) -> None:
        """Detect changes in data/context.jrvs and log them."""
        try:
            if not _CONTEXT_FILE.exists():
                return
            mtime = _CONTEXT_FILE.stat().st_mtime
            if self._context_mtime is None:
                self._context_mtime = mtime
                return
            if mtime != self._context_mtime:
                self._context_mtime = mtime
                logger.info("[PROACTIVE_CORE] data/context.jrvs atualizado. Recarregando contexto.")
                self._on_context_changed()
        except Exception as exc:
            logger.debug("[PROACTIVE_CORE] Erro ao verificar context.jrvs: %s", exc)

    def _check_jrvs_compile(self) -> None:
        """Periodically run JRVSCompiler.compile_all() based on OVERWATCH_COMPILE_INTERVAL_SEC.

        Uses the unified compile lock (data/jrvs/.compile.lock) to prevent concurrent runs
        with PolicyStore threshold-triggered compilations.
        """
        now = time.monotonic()
        if now - self._last_compile_ts < _OVERWATCH_COMPILE_INTERVAL_SEC:
            return
        self._last_compile_ts = now
        try:
            from app.core.meta.compile_lock import (  # noqa: PLC0415
                acquire_compile_lock,
                release_compile_lock,
            )
            from app.core.meta.jrvs_compiler import JRVSCompiler  # noqa: PLC0415

            jrvs_dir = os.getenv("JRVS_DIR", "data/jrvs")
            if not acquire_compile_lock(jrvs_dir):
                logger.debug("[PROACTIVE_CORE] JRVS compile_all bloqueado pelo lock unificado.")
                return
            try:
                compiler = JRVSCompiler()
                # Compile each module directly (lock already held by this method)
                modules = set(("llm", "tools", "meta")) | set(compiler._store.list_modules())
                for module_name in sorted(modules):
                    try:
                        compiler._compile_module_locked(module_name)
                    except Exception as exc:  # pragma: no cover
                        logger.error(
                            "[PROACTIVE_CORE] Falha ao compilar '%s': %s", module_name, exc
                        )
                logger.info("[PROACTIVE_CORE] JRVS compile_all concluído.")
            finally:
                release_compile_lock(jrvs_dir)
        except Exception as exc:
            logger.error("[PROACTIVE_CORE] Falha ao executar JRVS compile_all: %s", exc)

    def _check_inactivity(self) -> None:
        """After 30 min of inactivity, check if the user is present and suggest a task."""
        elapsed = time.monotonic() - self._last_activity_ts
        if elapsed < self._inactivity_timeout:
            return

        logger.info(
            "[PROACTIVE_CORE] Inatividade de %.0f min detectada. Verificando presença do usuário…",
            elapsed / 60,
        )

        # Reset timer so we don't fire repeatedly
        self._last_activity_ts = time.monotonic()

        # Use VisionAdapter to check if user is present
        try:
            vision = nexus.resolve("vision_adapter")
            if vision is not None:
                description = vision.capture_and_analyze(
                    "O usuário está presente na frente do computador? Responda apenas 'sim' ou 'não'."
                )
                if description and "sim" in description.lower():
                    logger.info("[PROACTIVE_CORE] Usuário presente. Sugerindo tarefa pendente.")
                    self._suggest_pending_task()
                else:
                    logger.info("[PROACTIVE_CORE] Usuário ausente ou indeterminado: %s", description)
        except Exception as exc:
            logger.debug("[PROACTIVE_CORE] VisionAdapter indisponível: %s", exc)

    # ------------------------------------------------------------------
    # Reaction helpers
    # ------------------------------------------------------------------

    def _on_context_changed(self) -> None:
        """React to a context.jrvs change."""
        try:
            ctx: Dict[str, Any] = document_store.read(_CONTEXT_FILE)
            logger.info("[PROACTIVE_CORE] Novo contexto carregado: %s chave(s).", len(ctx))
        except Exception as exc:
            logger.warning("[PROACTIVE_CORE] Falha ao ler context.jrvs: %s", exc)

    def _suggest_pending_task(self) -> None:
        """Fetch the next pending calendar task and notify the user."""
        try:
            pending = self._get_pending_calendar_tasks(limit=1)
            if pending:
                task = pending[0]
                msg = f"📅 [PROACTIVE_CORE] Tarefa pendente: {task}"
                logger.info(msg)
                self._notify(msg)
            else:
                logger.info("[PROACTIVE_CORE] Nenhuma tarefa pendente encontrada no calendário.")
        except Exception as exc:
            logger.debug("[PROACTIVE_CORE] Erro ao buscar tarefas: %s", exc)

    def _get_pending_calendar_tasks(self, limit: int = 5) -> List[str]:
        """
        Return pending tasks from ``data/context.jrvs`` (``pending_tasks`` key)
        or an empty list if unavailable.
        """
        tasks: List[str] = []
        try:
            if _CONTEXT_FILE.exists():
                ctx: Dict[str, Any] = document_store.read(_CONTEXT_FILE)
                raw = ctx.get("pending_tasks", [])
                tasks = [str(t) for t in raw[:limit]]
        except Exception:
            pass
        return tasks

    def _notify(self, message: str) -> None:
        """
        Send *message* through whatever notification channel is available
        (Telegram, voice, etc.).  Fails silently if none is available.
        """
        for adapter_id in ("telegram_adapter", "voice_provider"):
            try:
                adapter = nexus.resolve(adapter_id)
                if adapter is None:
                    continue
                if adapter_id == "telegram_adapter" and hasattr(adapter, "send_message"):
                    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
                    if chat_id:
                        adapter.send_message(chat_id, message)
                        return
                elif adapter_id == "voice_provider" and hasattr(adapter, "speak"):
                    adapter.speak(message)
                    return
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Tactical Perimeter (Phase 3 - Soldier Shield & Response)
    # ------------------------------------------------------------------

    def register_authorized_mac(self, mac: str) -> None:
        """Add *mac* to the set of authorised devices on the perimeter."""
        self._authorized_macs.add(mac.upper())

    def _check_tactical_perimeter(self) -> None:
        """
        Poll the Soldier registry for detected nearby devices and respond
        to any MAC addresses that are not in the authorised list.

        Runs every ``_PERIMETER_CHECK_EVERY`` ticks.
        """
        if self._tick_count % _PERIMETER_CHECK_EVERY != 0:
            return

        try:
            orchestrator = nexus.resolve("device_orchestrator_service")
            if orchestrator is None:
                return
            soldiers = orchestrator.list_soldiers()
        except Exception as exc:
            logger.debug("[PERIMETER] Orquestrador indisponível: %s", exc)
            return

        for soldier in soldiers:
            try:
                telemetry = nexus.resolve("soldier_telemetry_adapter")
                if telemetry is None:
                    continue
                # Retrieve latest telemetry from the orchestrator record
                # (nearby_devices are stored in the last ingest call)
                nearby = getattr(soldier, "_nearby_devices", [])
                for device in nearby:
                    mac = device.mac_address.upper()
                    if mac not in self._authorized_macs:
                        self._handle_intruder(mac, soldier.soldier_id, device)
            except Exception as exc:
                logger.debug(
                    "[PERIMETER] Erro ao verificar Soldado '%s': %s", soldier.soldier_id, exc
                )

    def _handle_intruder(self, mac: str, detected_by: str, device: Any) -> None:
        """
        Respond to an unauthorised device discovered on the perimeter.

        Steps:
          1. Block local communication with the intruder (Self-Defense).
          2. Notify the Commander via the notification pipeline.
          3. Record the forensic trace in VectorMemoryAdapter.
        """
        if mac in self._blocked_macs:
            return  # already handled

        logger.warning(
            "🚨 [PERIMETER] MAC não autorizado detectado: %s (por Soldado '%s')",
            mac,
            detected_by,
        )

        # 1. Self-defense: attempt to block via iptables (best-effort)
        self._block_mac(mac)

        # 2. Notify Commander
        msg = (
            f"🚨 ALERTA DE PERÍMETRO: dispositivo não autorizado detectado! "
            f"MAC={mac} | detectado por Soldado '{detected_by}' | "
            f"protocolo={getattr(device, 'protocol', 'desconhecido')}"
        )
        self._notify(msg)

        # 3. Store forensic trace in vector memory
        self._store_intruder_trace(mac, detected_by, device)

        self._blocked_macs.add(mac)

    def _block_mac(self, mac: str) -> None:
        """
        Attempt to block traffic from *mac* using iptables (Linux only).

        Fails silently on unsupported platforms or without root privileges.
        """
        try:
            import subprocess
            result = subprocess.run(
                ["iptables", "-A", "INPUT", "-m", "mac", "--mac-source", mac, "-j", "DROP"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("🛡️ [PERIMETER] MAC %s bloqueado via iptables.", mac)
            else:
                logger.debug(
                    "🛡️ [PERIMETER] iptables retornou %d para MAC %s: %s",
                    result.returncode,
                    mac,
                    result.stderr.decode(errors="replace"),
                )
        except FileNotFoundError:
            logger.debug("🛡️ [PERIMETER] iptables não disponível nesta plataforma.")
        except Exception as exc:
            logger.debug("🛡️ [PERIMETER] Bloqueio de MAC falhou: %s", exc)

    def _store_intruder_trace(self, mac: str, detected_by: str, device: Any) -> None:
        """Persist the intruder's forensic trace in VectorMemoryAdapter."""
        try:
            vector_memory = nexus.resolve("vector_memory_adapter")
            if vector_memory is None:
                return
            narrative = (
                f"Intrusão detectada: MAC={mac}, "
                f"protocolo={getattr(device, 'protocol', 'desconhecido')}, "
                f"SSID={getattr(device, 'ssid', None)}, "
                f"sinal={getattr(device, 'signal_dbm', None)} dBm, "
                f"detectado pelo Soldado '{detected_by}'."
            )
            vector_memory.store_event(
                narrative,
                metadata={
                    "event_type": "intruder_detected",
                    "mac_address": mac,
                    "detected_by": detected_by,
                },
            )
            logger.info("🧠 [PERIMETER] Rasto forense armazenado para MAC %s.", mac)
        except Exception as exc:
            logger.debug("🧠 [PERIMETER] Falha ao armazenar rasto forense: %s", exc)
