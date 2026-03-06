from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Perimeter Monitor mixin for OverwatchDaemon.

Provides tactical perimeter (MAC/ARP) monitoring methods
used by OverwatchDaemon via multiple inheritance.
"""

import logging
from typing import Any, Set

from app.core.nexus import nexus

logger = logging.getLogger(__name__)

_PERIMETER_CHECK_EVERY = 3  # ticks (every ~30 s)


class PerimeterMonitor(NexusComponent):
    """Mixin that adds tactical perimeter monitoring capabilities.

    Expects the host class to provide:
      self._tick_count, self._authorized_macs, self._blocked_macs, self._notify(msg)
    """

    def execute(self, context: dict) -> dict:
        return {"success": True, "component": "PerimeterMonitor"}

    # ------------------------------------------------------------------
    # Tactical Perimeter (Phase 3 - Soldier Shield & Response)
    # ------------------------------------------------------------------

    def register_authorized_mac(self, mac: str) -> None:
        """Add *mac* to the set of authorised devices on the perimeter."""
        self._authorized_macs.add(mac.upper())

    def _check_tactical_perimeter(self) -> None:
        """Poll the Soldier registry for detected nearby devices and respond
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
        """Respond to an unauthorised device discovered on the perimeter."""
        if mac in self._blocked_macs:
            return  # already handled

        logger.warning(
            "🚨 [PERIMETER] MAC não autorizado detectado: %s (por Soldado '%s')",
            mac,
            detected_by,
        )

        self._block_mac(mac)

        msg = (
            f"🚨 ALERTA DE PERÍMETRO: dispositivo não autorizado detectado! "
            f"MAC={mac} | detectado por Soldado '{detected_by}' | "
            f"protocolo={getattr(device, 'protocol', 'desconhecido')}"
        )
        self._notify(msg)

        self._store_intruder_trace(mac, detected_by, device)
        self._blocked_macs.add(mac)

    def _block_mac(self, mac: str) -> None:
        """Attempt to block traffic from *mac* using iptables (Linux only).

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
