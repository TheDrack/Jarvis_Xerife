# -*- coding: utf-8 -*-
"""Device Orchestrator Service - Authorized C2 registry for Soldier devices.

Implements the Soldier Mesh Protocol (Phase 1): a centralised registry of
"Authorized Soldiers" (user-owned devices such as PCs, Android phones via
Termux, Raspberry Pis, and IoT nodes) that connect to JARVIS Central via
secure WebSocket tunnels.

Each Soldier carries:
    - ``SoldierID``   – unique device identifier
    - ``PublicKey``   – RSA/Ed25519 public key for tunnel authentication
    - ``Status``      – Online / Offline / Reconnecting

The service is intentionally infrastructure-agnostic: it stores state in
memory and delegates persistence to an optional ``SoldierProvider`` port.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.application.ports.soldier_provider import SoldierProvider
from app.domain.models.soldier import (
    SoldierRecord,
    SoldierRegistration,
    SoldierStatus,
    TelemetryPayload,
)

logger = logging.getLogger(__name__)


class DeviceOrchestratorService(SoldierProvider):
    """
    Centralised Soldier registry and C2 orchestrator.

    Stores all Soldier records in an in-memory dict keyed by ``soldier_id``.
    An optional external ``SoldierProvider`` can be injected via the
    constructor to add database persistence without changing this service.

    Example usage::

        service = DeviceOrchestratorService()
        reg = SoldierRegistration(
            soldier_id="pi-zero-01",
            public_key="ssh-ed25519 AAAA...",
            device_type="raspberry_pi",
            alias="Sentinela Alpha",
        )
        soldier = service.register_soldier(reg)
        print(service.list_active_soldiers())
    """

    def __init__(self, external_provider: Optional[SoldierProvider] = None) -> None:
        """
        Args:
            external_provider: Optional persistence backend.  When provided,
                mutations are forwarded to both the in-memory store and the
                external provider.
        """
        self._registry: Dict[str, SoldierRecord] = {}
        self._external = external_provider

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict] = None) -> Dict:
        """
        Default execution: return a tactical overview of all Soldiers.

        Context keys (all optional):
            ``status_filter`` (str): "online" | "offline" | "reconnecting"
        """
        ctx = context or {}
        raw_filter = ctx.get("status_filter")
        status_filter: Optional[SoldierStatus] = None
        if raw_filter:
            try:
                status_filter = SoldierStatus(raw_filter)
            except ValueError:
                return {"success": False, "error": f"Invalid status_filter: '{raw_filter}'"}

        soldiers = self.list_soldiers(status_filter=status_filter)
        tactical_map = [self._soldier_to_map_entry(s) for s in soldiers]

        logger.info(
            "🗺️ [C2] Mapa Tático: %d Soldado(s) listado(s) (filtro=%s)",
            len(tactical_map),
            raw_filter or "none",
        )
        return {"success": True, "soldiers": tactical_map, "total": len(tactical_map)}

    # ------------------------------------------------------------------
    # SoldierProvider interface
    # ------------------------------------------------------------------

    def register_soldier(self, registration: SoldierRegistration) -> SoldierRecord:
        """Register or refresh a Soldier.  Existing records are updated in place."""
        existing = self._registry.get(registration.soldier_id)

        if existing:
            existing.public_key = registration.public_key
            existing.device_type = registration.device_type
            if registration.alias:
                existing.alias = registration.alias
            existing.status = SoldierStatus.ONLINE
            existing.last_seen = datetime.now(timezone.utc)
            record = existing
            logger.info("🔄 [C2] Soldado actualizado: %s", registration.soldier_id)
        else:
            record = SoldierRecord(
                soldier_id=registration.soldier_id,
                public_key=registration.public_key,
                device_type=registration.device_type,
                alias=registration.alias,
                status=SoldierStatus.ONLINE,
                registered_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            self._registry[registration.soldier_id] = record
            logger.info("✅ [C2] Novo Soldado registado: %s", registration.soldier_id)

        if self._external:
            self._external.register_soldier(registration)

        return record

    def get_soldier(self, soldier_id: str) -> Optional[SoldierRecord]:
        """Return the SoldierRecord for *soldier_id*, or None."""
        return self._registry.get(soldier_id)

    def update_status(self, soldier_id: str, status: SoldierStatus) -> bool:
        """Set the operational status of a Soldier."""
        record = self._registry.get(soldier_id)
        if not record:
            logger.warning("⚠️ [C2] update_status: Soldado '%s' não encontrado.", soldier_id)
            return False

        record.status = status
        record.last_seen = datetime.now(timezone.utc)
        logger.debug("🔔 [C2] Status actualizado: %s → %s", soldier_id, status.value)

        if self._external:
            self._external.update_status(soldier_id, status)

        return True

    def list_soldiers(self, status_filter: Optional[SoldierStatus] = None) -> List[SoldierRecord]:
        """List Soldiers, optionally filtered by status."""
        soldiers = list(self._registry.values())
        if status_filter is not None:
            soldiers = [s for s in soldiers if s.status == status_filter]
        return soldiers

    def deregister_soldier(self, soldier_id: str) -> bool:
        """Remove a Soldier from the registry."""
        if soldier_id not in self._registry:
            return False
        del self._registry[soldier_id]
        logger.info("🗑️ [C2] Soldado removido: %s", soldier_id)
        if self._external:
            self._external.deregister_soldier(soldier_id)
        return True

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def list_active_soldiers(self) -> List[SoldierRecord]:
        """Shortcut: return only ONLINE Soldiers."""
        return self.list_soldiers(status_filter=SoldierStatus.ONLINE)

    def apply_telemetry(self, payload: TelemetryPayload) -> bool:
        """
        Merge a telemetry bundle into the registry entry for the sender.

        Stores location, system state, and last-seen timestamp.  Returns
        False if the Soldier is not registered.
        """
        record = self._registry.get(payload.soldier_id)
        if not record:
            logger.warning(
                "⚠️ [C2] apply_telemetry: Soldado '%s' não registado — descartado.",
                payload.soldier_id,
            )
            return False

        if payload.location:
            record.lat = payload.location.lat
            record.lon = payload.location.lon
            record.last_ip = payload.location.ip

        if payload.system_state:
            record.battery_pct = payload.system_state.battery_pct
            record.cpu_pct = payload.system_state.cpu_pct
            record.ram_pct = payload.system_state.ram_pct

        record.last_seen = datetime.now(timezone.utc)
        record.status = SoldierStatus.ONLINE

        logger.debug(
            "📡 [C2] Telemetria aplicada: %s (lat=%s, lon=%s, bat=%s%%)",
            payload.soldier_id,
            record.lat,
            record.lon,
            record.battery_pct,
        )
        return True

    def get_tactical_map(self) -> List[Dict]:
        """Return all Soldiers formatted for display on a Tactical Map."""
        return [self._soldier_to_map_entry(s) for s in self._registry.values()]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _soldier_to_map_entry(soldier: SoldierRecord) -> Dict:
        return {
            "soldier_id": soldier.soldier_id,
            "alias": soldier.alias or soldier.soldier_id,
            "device_type": soldier.device_type,
            "status": soldier.status.value,
            "lat": soldier.lat,
            "lon": soldier.lon,
            "last_ip": soldier.last_ip,
            "battery_pct": soldier.battery_pct,
            "cpu_pct": soldier.cpu_pct,
            "ram_pct": soldier.ram_pct,
            "last_seen": soldier.last_seen.isoformat() if soldier.last_seen else None,
        }
