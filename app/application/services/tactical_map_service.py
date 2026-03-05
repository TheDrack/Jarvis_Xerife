# -*- coding: utf-8 -*-
"""Tactical Map Service - Intelligence consolidation for all active Soldiers.

Implements Phase 4 of the Tactical Mesh: consolidates GPS coordinates, IP
addresses, system metrics, and monitored SSIDs from all registered Soldiers
into a unified tactical picture.

The service can generate:
  - A structured dict representation of the tactical map.
  - A human-readable status report string for voice/chat output.

Architecture (Hexagonal):
    - Lives in the Application layer.
    - Reads from ``DeviceOrchestratorService`` (in-memory registry).
    - Optionally queries ``SoldierTelemetryAdapter`` to trigger a fresh
      telemetry collection on demand.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.application.services.device_orchestrator_service import DeviceOrchestratorService
from app.core.nexus import NexusComponent
from app.domain.models.soldier import SoldierRecord, SoldierStatus

logger = logging.getLogger(__name__)


class TacticalMapService(NexusComponent):
    """
    Consolidates Soldier intelligence into a unified tactical map.

    Args:
        orchestrator: The ``DeviceOrchestratorService`` managing the Soldier
            registry.  Resolved via Nexus if not provided.
    """

    def __init__(
        self,
        orchestrator: Optional[DeviceOrchestratorService] = None,
    ) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict] = None) -> Dict:
        """
        Default execution: return the full tactical map and a status report.

        Context keys (all optional):
            ``report_only`` (bool): If True, return only the text report.
            ``status_filter`` (str): ``"online"`` | ``"offline"`` | ``"reconnecting"``.
        """
        ctx = context or {}
        self._ensure_orchestrator()

        if ctx.get("report_only"):
            return {"success": True, "report": self.generate_report()}

        raw_filter = ctx.get("status_filter")
        status_filter: Optional[SoldierStatus] = None
        if raw_filter:
            try:
                status_filter = SoldierStatus(raw_filter)
            except ValueError:
                return {"success": False, "error": f"Invalid status_filter: '{raw_filter}'"}

        tactical_map = self.get_tactical_map(status_filter=status_filter)
        report = self.generate_report()
        return {
            "success": True,
            "tactical_map": tactical_map,
            "report": report,
            "total": len(tactical_map),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tactical_map(
        self, status_filter: Optional[SoldierStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        Return a structured list of all Soldiers enriched with tactical metadata.

        Args:
            status_filter: When provided, include only Soldiers with this status.

        Returns:
            List of tactical map entries (one dict per Soldier).
        """
        self._ensure_orchestrator()
        soldiers = self._orchestrator.list_soldiers(status_filter=status_filter)  # type: ignore[union-attr]
        return [self._enrich_soldier(s) for s in soldiers]

    def generate_report(self) -> str:
        """
        Generate a human-readable tactical status report.

        Example output::

            Estado: 3 Soldado(s) em Modo SENTINELA.
            Localização: [(-23.5505, -46.6333), 10.0.0.2, Alpha-PC].
            Redes Sob Monitorização: [HomeWifi, OfficeNet].

        Returns:
            Formatted status string.
        """
        self._ensure_orchestrator()
        all_soldiers = self._orchestrator.list_soldiers()  # type: ignore[union-attr]
        online = [s for s in all_soldiers if s.status == SoldierStatus.ONLINE]

        if not all_soldiers:
            return "Estado: Nenhum Soldado registado."

        location_parts: List[str] = []
        ssids: List[str] = []

        for soldier in online:
            if soldier.lat is not None and soldier.lon is not None:
                location_parts.append(f"({soldier.lat:.4f}, {soldier.lon:.4f})")
            elif soldier.last_ip:
                location_parts.append(soldier.last_ip)
            else:
                location_parts.append(soldier.alias or soldier.soldier_id)

            # Collect SSIDs from nearby device metadata stored in soldier extra
            soldier_ssids = self._extract_ssids(soldier)
            ssids.extend(s for s in soldier_ssids if s not in ssids)

        location_str = f"[{', '.join(location_parts)}]" if location_parts else "Desconhecida"
        ssids_str = f"[{', '.join(ssids)}]" if ssids else "N/D"

        return (
            f"Estado: {len(online)} Soldado(s) em Modo SENTINELA. "
            f"Localização: {location_str}. "
            f"Redes Sob Monitorização: {ssids_str}."
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_orchestrator(self) -> None:
        """Lazily resolve the orchestrator via Nexus if not injected."""
        if self._orchestrator is None:
            from app.core.nexus import nexus

            self._orchestrator = nexus.resolve("device_orchestrator_service")

    @staticmethod
    def _enrich_soldier(soldier: SoldierRecord) -> Dict[str, Any]:
        """Convert a ``SoldierRecord`` into a tactical map entry."""
        return {
            "soldier_id": soldier.soldier_id,
            "alias": soldier.alias or soldier.soldier_id,
            "device_type": soldier.device_type,
            "status": soldier.status.value,
            "location": {
                "lat": soldier.lat,
                "lon": soldier.lon,
                "ip": soldier.last_ip,
            },
            "system": {
                "battery_pct": soldier.battery_pct,
                "cpu_pct": soldier.cpu_pct,
                "ram_pct": soldier.ram_pct,
            },
            "last_seen": soldier.last_seen.isoformat() if soldier.last_seen else None,
        }

    @staticmethod
    def _extract_ssids(soldier: SoldierRecord) -> List[str]:
        """
        Extract known Wi-Fi SSIDs from the soldier record.

        The SSIDs are stored by ``SoldierTelemetryAdapter`` in an optional
        ``_nearby_wifi_ssids`` attribute (a plain list) that is set after
        telemetry ingestion.  This is a best-effort extraction.
        """
        try:
            return list(getattr(soldier, "_nearby_wifi_ssids", []))
        except AttributeError:
            return []
