from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Resource Monitor mixin for OverwatchDaemon.

Provides CPU/RAM reactive and predictive monitoring methods
used by OverwatchDaemon via multiple inheritance.
"""

import logging
from typing import TYPE_CHECKING, Deque

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (resource-monitoring specific)
# ---------------------------------------------------------------------------
_CPU_CHECK_EVERY = 6              # ticks (every ~60 s)
_PREDICTIVE_CPU_THRESHOLD = 80.0  # %
_PREDICTIVE_RAM_THRESHOLD = 85.0  # %


class ResourceMonitor(NexusComponent):
    """Mixin that adds CPU/RAM reactive and predictive monitoring capabilities.

    Expects the host class to provide:
      self._tick_count, self._cpu_threshold, self._ram_threshold,
      self._cpu_history, self._ram_history, self._notify(msg)
    """

    def execute(self, context: dict) -> dict:
        return {"success": True, "component": "ResourceMonitor"}

    # ------------------------------------------------------------------
    # Monitoring tasks
    # ------------------------------------------------------------------

    def _check_resources(self) -> None:
        """Monitor CPU and RAM; warn if either exceeds the threshold.

        Também mantém janela deslizante e dispara alerta preditivo (MELHORIA 6).
        """
        if self._tick_count % _CPU_CHECK_EVERY != 0:
            return

        try:
            import psutil

            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent

            # Reactive alerts (threshold exceeded right now)
            if cpu > self._cpu_threshold:
                msg = f"⚠️ CPU em {cpu:.0f}% — uso elevado detectado."
                logger.warning("[PROACTIVE_CORE] %s", msg)
                self._notify(msg)

            if ram > self._ram_threshold:
                msg = f"⚠️ RAM em {ram:.0f}% — memória alta detectada."
                logger.warning("[PROACTIVE_CORE] %s", msg)
                self._notify(msg)

            # Update sliding windows
            self._cpu_history.append(cpu)
            self._ram_history.append(ram)

            # Predictive checks
            trend = self._compute_trend(self._cpu_history, self._ram_history)
            self._check_predictive_alerts(cpu, ram, trend)
            self._write_context_trend(cpu, ram, trend)

        except ImportError:
            logger.debug(
                "[PROACTIVE_CORE] psutil não instalado; monitoramento de recursos desativado."
            )
        except Exception as exc:
            logger.debug("[PROACTIVE_CORE] Erro ao verificar recursos: %s", exc)

    # ------------------------------------------------------------------
    # Predictive helpers (MELHORIA 6)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_trend(
        cpu_hist: "Deque[float]",
        ram_hist: "Deque[float]",
    ) -> str:
        """Calcula a tendência linear a partir das janelas deslizantes.

        Compara a média das últimas 5 leituras com a média das 5 anteriores.
        Retorna: ``'rising'``, ``'falling'``, ou ``'stable'``.
        """
        history = list(cpu_hist)
        if len(history) < 10:
            return "stable"
        older = history[:5]
        newer = history[5:]
        avg_old = sum(older) / len(older)
        avg_new = sum(newer) / len(newer)
        delta = avg_new - avg_old
        if delta > 5.0:
            return "rising"
        if delta < -5.0:
            return "falling"
        return "stable"

    def _check_predictive_alerts(self, cpu: float, ram: float, trend: str) -> None:
        """Dispara notificação preventiva se tendência de crescimento ultrapassar limiares."""
        if trend != "rising":
            return

        cpu_list = list(self._cpu_history)
        ram_list = list(self._ram_history)
        if len(cpu_list) < 10 or len(ram_list) < 10:
            return

        # Projeção simples: última leitura + delta médio por leitura
        cpu_delta = (cpu_list[-1] - cpu_list[0]) / (len(cpu_list) - 1)
        ram_delta = (ram_list[-1] - ram_list[0]) / (len(ram_list) - 1)
        cpu_proj = cpu_list[-1] + cpu_delta
        ram_proj = ram_list[-1] + ram_delta

        if cpu_proj >= _PREDICTIVE_CPU_THRESHOLD:
            msg = (
                f"[PROACTIVE_CORE][PREDICTIVE] ⚠️ CPU projetada em {cpu_proj:.1f}% "
                f"no próximo ciclo — tendência de alta detectada."
            )
            logger.warning(msg)
            self._notify(msg)

        if ram_proj >= _PREDICTIVE_RAM_THRESHOLD:
            msg = (
                f"[PROACTIVE_CORE][PREDICTIVE] ⚠️ RAM projetada em {ram_proj:.1f}% "
                f"no próximo ciclo — tendência de alta detectada."
            )
            logger.warning(msg)
            self._notify(msg)

    def _write_context_trend(self, cpu: float, ram: float, trend: str) -> None:
        """Atualiza data/context.json com o campo trend e system_health (MELHORIA 6)."""
        try:
            from app.domain.context.context_manager import ContextManager  # lazy
            ctx_mgr = ContextManager()
            ctx_mgr.write_context(
                {
                    "system_health": {
                        "cpu_percent": cpu,
                        "ram_percent": ram,
                        "status": (
                            "critical"
                            if cpu > self._cpu_threshold or ram > self._ram_threshold
                            else "warning"
                            if cpu > _PREDICTIVE_CPU_THRESHOLD or ram > _PREDICTIVE_RAM_THRESHOLD
                            else "healthy"
                        ),
                    },
                    "trend": trend,
                }
            )
        except Exception as exc:
            logger.debug("[PROACTIVE_CORE] Falha ao escrever trend no context.json: %s", exc)
