# -*- coding: utf-8 -*-
"""Overwatch Daemon — Orquestrador de monitoramento proativo.
CORREÇÃO: Erros de sintaxe/indentação mobile e integração de Health Check.
"""
import logging
import os
import threading
import time
import subprocess
from typing import Optional, Set, Any, Dict

from app.core.nexus import nexus, NexusComponent
from .overwatch_resource_monitor import ResourceMonitor
from .overwatch_perimeter import PerimeterMonitor
from .overwatch_inactivity import InactivityMonitor
from .overwatch_context import ContextMonitor, get_pending_tasks

logger = logging.getLogger(__name__)

# Constantes
_POLL_INTERVAL = 10
_PERIMETER_CHECK_EVERY = 3
_COMPILE_INTERVAL = float(os.getenv("OVERWATCH_COMPILE_INTERVAL_SEC", "600"))
_CONSOLIDATION_INTERVAL = float(os.getenv("OVERWATCH_CONSOLIDATION_MIN", "15"))

class OverwatchDaemon(ResourceMonitor, PerimeterMonitor, NexusComponent):
    """Daemon de monitoramento proativo do JARVIS."""

    def __init__(
        self,
        poll_interval: float = _POLL_INTERVAL,
        cpu_threshold: float = 85.0,
        ram_threshold: float = 85.0,
        inactivity_timeout: float = 1800,
        authorized_macs: Optional[Set[str]] = None,
    ) -> None:
        super().__init__()

        # Configurações
        self._poll_interval = poll_interval
        self._cpu_threshold = cpu_threshold
        self._ram_threshold = ram_threshold

        # Estado
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_count = 0
        self._last_compile_ts = 0.0
        self._last_consolidation_ts = 0.0        
        
        # Monitores especializados
        self._inactivity = InactivityMonitor(timeout_seconds=inactivity_timeout)
        self._context = ContextMonitor()

        # Perímetro
        self._authorized_macs = {m.upper() for m in (authorized_macs or set())}
        self._blocked_macs: Set[str] = set()

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        action = ctx.get("action", "status")

        if action == "notify_activity":
            self._inactivity.reset_timer()
            return {"success": True, "action": "activity_notified"}

        return {"success": True, "running": self._running, "tick": self._tick_count}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="OverwatchDaemon"
        )
        self._thread.start()
        logger.info("[Overwatch] Daemon iniciado.")

    def stop(self) -> None:
        self._running = False
        logger.info("[Overwatch] Daemon parando...")

    def notify_activity(self) -> None:
        self._inactivity.reset_timer()

    def _run_loop(self) -> None:
        logger.info("[Overwatch] Loop principal iniciado.")
        while self._running:
            self._tick_count += 1
            try:
                self._check_resources()
                self._check_context()
                self._check_inactivity()
                self._check_perimeter()
                self._check_compile()
                self._maybe_consolidate_memory()
            except Exception as exc:
                logger.error("[Overwatch] Erro no loop: %s", exc)

            time.sleep(self._poll_interval)
        logger.info("[Overwatch] Loop encerrado.")

    def _check_context(self) -> None:
        changed = self._context.check_changes(
            on_change_callback=self._on_context_changed,
        )
        if changed:
            logger.info("[Overwatch] Contexto recarregado.")

    def _check_inactivity(self) -> None:
        inactive = self._inactivity.check_inactivity(
            suggest_task_callback=self._suggest_task,
        )
        if inactive:
            logger.info("[Overwatch] Inatividade detectada.")

    def _check_perimeter(self) -> None:
        if self._tick_count % _PERIMETER_CHECK_EVERY != 0:
            return

        soldiers = self._list_soldiers()
        for soldier in soldiers:
            nearby = getattr(soldier, "_nearby_devices", [])
            for device in nearby:
                mac = device.mac_address.upper()
                if mac not in self._authorized_macs:
                    self._handle_intruder(mac, soldier.soldier_id, device)

    def _check_compile(self) -> None:
        now = time.monotonic()
        if now - self._last_compile_ts < _COMPILE_INTERVAL:
            return
        self._last_compile_ts = now
        self._compile_modules()

    def _maybe_consolidate_memory(self) -> None:
        now = time.monotonic()
        interval_sec = _CONSOLIDATION_INTERVAL * 60

        if now - self._last_consolidation_ts < interval_sec:
            return

        self._last_consolidation_ts = now

        try:
            service = nexus.resolve("memory_consolidation_service")
            if not service or getattr(service, "__is_cloud_mock__", False):
                return

            vector_adapter = nexus.resolve("vector_memory_adapter")
            if not vector_adapter:
                return

            # Health Check do Adapter antes de liberar a RAM
            if hasattr(vector_adapter, "is_healthy"):
                if not vector_adapter.is_healthy():
                    logger.warning("[Overwatch] VectorAdapter offline. Consolidação adiada.")
                    return

            result = service.execute({"max_age_hours": 24})
            if result.get("success"):
                logger.info("[Overwatch] Consolidação concluída.")
        except Exception as exc:
            logger.debug(f"[Overwatch] Falha na consolidação: {exc}")

    def _handle_intruder(self, mac: str, soldier_id: str, device: Any) -> None:
        if mac in self._blocked_macs:
            return

        logger.warning("🚨 [Perímetro] MAC não autorizado: %s", mac)
        self._block_mac(mac)
        self._notify(f"ALERTA: MAC não autorizado {mac}")
        self._store_trace(mac, soldier_id, device)
        self._blocked_macs.add(mac)

    def _block_mac(self, mac: str) -> None:
        """Tenta bloquear MAC via iptables."""
        try:
            result = subprocess.run(
                ["iptables", "-A", "INPUT", "-m", "mac", "--mac-source", mac, "-j", "DROP"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                logger.info("🛡️ [Perímetro] MAC %s bloqueado.", mac)
        except Exception:
            pass

    def _on_context_changed(self) -> None:
        try:
            ctx = self._context.load_context()
            logger.info("[Overwatch] Contexto: %d chaves.", len(ctx))
        except Exception as exc:
            logger.warning("[Overwatch] Falha ao ler contexto: %s", exc)

    def _suggest_task(self) -> None:
        try:
            tasks = get_pending_tasks(limit=1)
            if tasks:
                self._notify(f"Tarefa pendente: {tasks[0]}")
        except Exception as exc:
            logger.debug("[Overwatch] Falha ao sugerir tarefa: %s", exc)

    def _list_soldiers(self) -> list:
        try:
            orch = nexus.resolve("device_orchestrator_service")
            return orch.list_soldiers() if orch else []
        except Exception:
            return []

    def _store_trace(self, mac: str, soldier_id: str, device: Any) -> None:
        try:
            vector_mem = nexus.resolve("vector_memory_adapter")
            if vector_mem:
                vector_mem.store_event(f"Intrusão: MAC={mac}", metadata={"mac": mac})
        except Exception:
            pass

    def _compile_modules(self) -> None:
        try:
            from app.core.meta.compile_lock import acquire_compile_lock, release_compile_lock
            from app.core.meta.jrvs_compiler import JRVSCompiler
            jrvs_dir = os.getenv("JRVS_DIR", "data/jrvs")
            if not acquire_compile_lock(jrvs_dir):
                return
            try:
                compiler = JRVSCompiler()
                modules = set(("llm", "tools", "meta")) | set(compiler._store.list_modules())
                for mod in sorted(modules):
                    compiler._compile_module_locked(mod)
                logger.info("[Overwatch] Compile concluído.")
            finally:
                release_compile_lock(jrvs_dir)
        except Exception as exc:
            logger.error("[Overwatch] Falha no compile: %s", exc)

    def _notify(self, message: str) -> None:
        for adapter_id in ("telegram_adapter", "voice_provider"):
            try:
                adapter = nexus.resolve(adapter_id)
                if adapter and hasattr(adapter, "send_message"):
                    chat_id = os.getenv("TELEGRAM_CHAT_ID")
                    if chat_id:
                        adapter.send_message(chat_id, message)
                        return
            except Exception:
                pass

# Compatibilidade
Overwatch = OverwatchDaemon
