# -*- coding: utf-8 -*-
"""Soldier Telemetry Adapter - Sensor extension for Soldier Mesh (Phase 2).

This adapter bridges the gap between raw telemetry received from Soldier
devices and JARVIS internal memory/orchestration:

1. Validates incoming TelemetryPayload with Pydantic.
2. Forwards the payload to ``DeviceOrchestratorService`` to keep the
   in-memory Soldier registry up to date.
3. Converts the telemetry bundle into a human-readable narrative and stores
   it in ``VectorMemoryAdapter`` as a contextual event so that the LLM can
   reason about Soldier locations and health over time.

Hardware access (GPS, Bluetooth, CPU/RAM readings) is intentionally left
as a set of *swappable collectors* so the adapter works on any platform
(Linux, Android/Termux, Raspberry Pi) simply by changing the collector
implementation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.application.ports.memory_provider import MemoryProvider
from app.application.services.device_orchestrator_service import DeviceOrchestratorService
from app.core.nexuscomponent import NexusComponent
from app.domain.models.soldier import (
    LocationPayload,
    NearbyDevice,
    SystemState,
    TelemetryPayload,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional system-metrics collectors (graceful no-ops when libs are absent)
# ---------------------------------------------------------------------------


def _collect_system_state(soldier_id: str) -> Optional[SystemState]:
    """Try to read CPU / RAM / battery via psutil.  Returns None if unavailable."""
    try:
        import psutil  # type: ignore

        battery = psutil.sensors_battery()
        return SystemState(
            soldier_id=soldier_id,
            cpu_pct=psutil.cpu_percent(interval=0.5),
            ram_pct=psutil.virtual_memory().percent,
            battery_pct=battery.percent if battery else None,
        )
    except Exception:  # psutil not installed or platform unsupported
        return None


def _collect_location(soldier_id: str) -> Optional[LocationPayload]:
    """Try to obtain public IP as a fallback location source."""
    try:
        import socket

        ip = socket.gethostbyname(socket.gethostname())
        return LocationPayload(soldier_id=soldier_id, ip=ip)
    except Exception:
        return None


def _collect_nearby_devices() -> List[NearbyDevice]:
    """Stub: real implementations would call iwlist / bluepy / scapy.

    Returns an empty list on platforms where scanning is not available.
    This ensures the adapter functions without root permissions or hardware.
    """
    return []


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class SoldierTelemetryAdapter(NexusComponent):
    """
    Bidirectional telemetry bridge for Soldier devices.

    Receives telemetry bundles (either from a remote Soldier via WebSocket or
    generated locally by calling ``collect_and_report``), validates them,
    updates the Soldier registry, and injects them into vector memory as
    contextual events.

    Args:
        orchestrator: The ``DeviceOrchestratorService`` managing the Soldier
            registry.
        memory: Optional ``MemoryProvider`` (e.g. ``VectorMemoryAdapter``)
            used to store telemetry as searchable narrative events.
    """

    def __init__(
        self,
        orchestrator: Optional[DeviceOrchestratorService] = None,
        memory: Optional[MemoryProvider] = None,
    ) -> None:
        self._orchestrator = orchestrator or DeviceOrchestratorService()
        self._memory = memory

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a raw telemetry context dict.

        Context keys:
            ``payload`` (dict): Raw telemetry data to validate and ingest.
            ``soldier_id`` (str): If payload is absent, collect locally.
        """
        ctx = context or {}
        raw_payload = ctx.get("payload")

        if raw_payload:
            try:
                payload = TelemetryPayload(**raw_payload)
            except Exception as exc:
                logger.error("❌ [Telemetry] Payload inválido: %s", exc)
                return {"success": False, "error": str(exc)}
            return self.ingest(payload)

        soldier_id = ctx.get("soldier_id")
        if soldier_id:
            return self.collect_and_report(soldier_id)

        return {"success": False, "error": "Context must contain 'payload' or 'soldier_id'."}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(self, payload: TelemetryPayload) -> Dict[str, Any]:
        """
        Validate, apply, and persist a ``TelemetryPayload`` from a Soldier.

        Steps:
        1. Apply the payload to the Soldier registry.
        2. Generate a narrative summary and store it in vector memory.

        Args:
            payload: Validated telemetry bundle.

        Returns:
            Result dict with ``success``, ``soldier_id``, and ``event_id``.
        """
        applied = self._orchestrator.apply_telemetry(payload)
        if not applied:
            return {
                "success": False,
                "error": f"Soldado '{payload.soldier_id}' não registado.",
            }

        narrative = self._build_narrative(payload)
        event_id: Optional[str] = None
        if self._memory:
            event_id = self._memory.store_event(
                narrative,
                metadata={
                    "soldier_id": payload.soldier_id,
                    "event_type": "telemetry",
                    "timestamp": payload.timestamp.isoformat(),
                },
            )
            logger.debug(
                "🧠 [Telemetry] Evento armazenado em memória vectorial: %s", event_id
            )

        logger.info(
            "📡 [Telemetry] Ingestão completa: %s | %d vizinho(s) | memória=%s",
            payload.soldier_id,
            len(payload.nearby_devices),
            "✅" if event_id else "❌",
        )
        return {
            "success": True,
            "soldier_id": payload.soldier_id,
            "event_id": event_id,
            "narrative": narrative,
        }

    def collect_and_report(self, soldier_id: str) -> Dict[str, Any]:
        """
        Collect local sensor data and ingest it as a TelemetryPayload.

        This method is intended to run on the *Soldier* side.  It gathers
        CPU/RAM/battery, IP address, and nearby device information using
        whatever platform libraries are available, then calls ``ingest``.

        Args:
            soldier_id: The Soldier's registered ID.

        Returns:
            Result dict from ``ingest``.
        """
        location = _collect_location(soldier_id)
        system_state = _collect_system_state(soldier_id)
        nearby = _collect_nearby_devices()

        payload = TelemetryPayload(
            soldier_id=soldier_id,
            location=location,
            system_state=system_state,
            nearby_devices=nearby,
            timestamp=datetime.now(timezone.utc),
        )
        return self.ingest(payload)

    def get_soldier_location(self, soldier_id: str) -> Optional[Dict[str, Any]]:
        """
        Return the last known location of a Soldier from the registry.

        Args:
            soldier_id: The unique Soldier identifier.

        Returns:
            Dict with ``lat``, ``lon``, ``last_ip``, ``last_seen``, or None.
        """
        soldier = self._orchestrator.get_soldier(soldier_id)
        if not soldier:
            return None
        return {
            "soldier_id": soldier.soldier_id,
            "lat": soldier.lat,
            "lon": soldier.lon,
            "last_ip": soldier.last_ip,
            "last_seen": soldier.last_seen.isoformat() if soldier.last_seen else None,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_narrative(payload: TelemetryPayload) -> str:
        """Convert a TelemetryPayload into a natural-language summary."""
        parts: List[str] = [f"Soldado '{payload.soldier_id}'"]

        if payload.location:
            loc = payload.location
            if loc.lat is not None and loc.lon is not None:
                parts.append(f"localizado em ({loc.lat:.4f}, {loc.lon:.4f})")
            elif loc.ip:
                parts.append(f"com IP {loc.ip}")

        if payload.system_state:
            ss = payload.system_state
            metrics: List[str] = []
            if ss.battery_pct is not None:
                metrics.append(f"bateria {ss.battery_pct:.0f}%")
            if ss.cpu_pct is not None:
                metrics.append(f"CPU {ss.cpu_pct:.0f}%")
            if ss.ram_pct is not None:
                metrics.append(f"RAM {ss.ram_pct:.0f}%")
            if metrics:
                parts.append("estado do sistema: " + ", ".join(metrics))

        if payload.nearby_devices:
            wifi = [d for d in payload.nearby_devices if d.protocol == "wifi"]
            bt = [d for d in payload.nearby_devices if d.protocol == "bluetooth"]
            if wifi:
                parts.append(f"{len(wifi)} dispositivo(s) Wi-Fi próximo(s)")
            if bt:
                parts.append(f"{len(bt)} dispositivo(s) Bluetooth próximo(s)")

        parts.append(f"às {payload.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        return ". ".join(parts) + "."
