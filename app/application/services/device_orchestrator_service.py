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

The service supports hybrid persistence (Memory + SQLite via SQLModel).
An optional ``db_url`` enables SQLite persistence so the registry survives
restarts.  When the DB is unavailable the service falls back to memory-only
mode without interrupting operation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.application.ports.soldier_provider import SoldierProvider
from app.domain.models.soldier import (
    SoldierRecord,
    SoldierRegistration,
    SoldierStatus,
    TelemetryPayload,
)

try:
    from sqlmodel import Field, Session, SQLModel, create_engine, select

    _SQLMODEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SQLMODEL_AVAILABLE = False
    Field = Any  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# SQLite persistence model
# ---------------------------------------------------------------------------

if _SQLMODEL_AVAILABLE:

    class SoldierDB(SQLModel, table=True):  # type: ignore[call-arg]
        """SQLite row that mirrors a :class:`SoldierRecord`."""

        __tablename__ = "soldiers"

        soldier_id: str = Field(primary_key=True)
        public_key: str = ""
        device_type: str = "unknown"
        alias: Optional[str] = None
        status: str = SoldierStatus.OFFLINE.value
        registered_at: Optional[str] = None
        last_seen: Optional[str] = None
        lat: Optional[float] = None
        lon: Optional[float] = None
        last_ip: Optional[str] = None
        battery_pct: Optional[float] = None
        cpu_pct: Optional[float] = None
        ram_pct: Optional[float] = None


logger = logging.getLogger(__name__)


class DeviceOrchestratorService(SoldierProvider):
    """
    Centralised Soldier registry and C2 orchestrator.

    Stores all Soldier records in an in-memory dict keyed by ``soldier_id``.
    Supports optional SQLite persistence via ``db_url`` so the registry
    survives process restarts.  When the DB is unavailable the service
    operates in memory-only mode without interrupting normal operation.

    Example usage::

        service = DeviceOrchestratorService(db_url="sqlite:///soldiers.db")
        service.bootstrap()  # Load persisted soldiers into memory
        reg = SoldierRegistration(
            soldier_id="pi-zero-01",
            public_key="ssh-ed25519 AAAA...",
            device_type="raspberry_pi",
            alias="Sentinela Alpha",
        )
        soldier = service.register_soldier(reg)
        print(service.list_active_soldiers())
    """

    def __init__(
        self,
        external_provider: Optional[SoldierProvider] = None,
        db_url: Optional[str] = None,
    ) -> None:
        """
        Args:
            external_provider: Optional persistence backend.  When provided,
                mutations are forwarded to both the in-memory store and the
                external provider.
            db_url: SQLAlchemy-compatible DB URL for hybrid persistence
                (e.g. ``"sqlite:///soldiers.db"``).  When *None* the service
                operates in memory-only mode.
        """
        self._registry: Dict[str, SoldierRecord] = {}
        self._external = external_provider
        self._engine: Optional[Any] = None

        if db_url and _SQLMODEL_AVAILABLE:
            try:
                self._engine = create_engine(db_url, echo=False)
                SQLModel.metadata.create_all(self._engine)
                logger.info("🗄️ [C2] SQLite persistence activada: %s", db_url)
            except Exception as exc:
                logger.error(
                    "❌ [C2] Falha ao inicializar DB ('%s'). Modo memory-only. Erro: %s",
                    db_url,
                    exc,
                )
                self._engine = None

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

        self._save_to_db(record)
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

        self._save_to_db(record)
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

    def dispatch(
        self, task: Dict[str, Any], capability: Optional[str] = None
    ) -> Dict[str, Any]:
        """Route *task* to an available soldier that supports *capability*.

        Lookup order:
        1. :class:`~app.application.services.soldier_registry.SoldierRegistry`
           — checks connected bridge devices by capability tag.
        2. In-memory ``_registry`` — falls back to any ONLINE soldier when the
           SoldierRegistry has no match or is unavailable.
        3. Local / cloud execution — returns a fallback dict when no soldier
           is reachable.

        Args:
            task:       Task dict with at least an ``"action"`` key.
            capability: Optional capability tag to filter eligible soldiers.

        Returns:
            Dispatch result dict.
        """
        # --- 1. Try SoldierRegistry via Nexus (connected bridge soldiers) ---
        try:
            from app.core.nexus import nexus

            registry = nexus.resolve("soldier_registry")
            candidates = registry.get_available_soldiers(capability)
            if candidates:
                soldier_id = candidates[0]["soldier_id"]
                logger.info(
                    "🚀 [C2] dispatch → SoldierRegistry soldier '%s' (cap=%s)", soldier_id, capability
                )
                return {"success": True, "dispatched_to": soldier_id, "via": "soldier_registry", "task": task}
        except Exception as exc:
            logger.debug("[C2] SoldierRegistry lookup falhou: %s", exc)

        # --- 2. Fallback: in-memory registry ---
        online = self.list_active_soldiers()
        if capability:
            # DeviceOrchestratorService does not store capabilities — skip filter
            pass
        if online:
            soldier_id = online[0].soldier_id
            logger.info("🚀 [C2] dispatch → local registry soldier '%s'", soldier_id)
            return {"success": True, "dispatched_to": soldier_id, "via": "local_registry", "task": task}

        # --- 3. No soldiers available ---
        logger.warning("⚠️ [C2] dispatch: nenhum soldado disponível para capability='%s'", capability)
        return {
            "success": False,
            "error": "no_soldiers_available",
            "capability": capability,
            "task": task,
        }

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
        self._save_to_db(record)
        return True

    def get_tactical_map(self) -> List[Dict]:
        """Return all Soldiers formatted for display on a Tactical Map."""
        return [self._soldier_to_map_entry(s) for s in self._registry.values()]

    def bootstrap(self) -> None:
        """Load previously persisted ONLINE/RECONNECTING Soldiers into memory.

        Call this once after construction (e.g. during application startup)
        so the in-memory registry is pre-populated from the SQLite store.
        """
        loaded = self._load_from_db()
        if loaded:
            logger.info("🔁 [C2] Bootstrap: %d soldado(s) carregado(s) do DB.", loaded)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save_to_db(self, record: SoldierRecord) -> None:
        """Persist *record* to SQLite.  Silently skips when DB is not configured."""
        if self._engine is None or not _SQLMODEL_AVAILABLE:
            return
        try:
            with Session(self._engine) as session:
                row = session.get(SoldierDB, record.soldier_id)
                if row is None:
                    row = SoldierDB(soldier_id=record.soldier_id)
                    session.add(row)
                row.public_key = record.public_key
                row.device_type = record.device_type
                row.alias = record.alias
                row.status = record.status.value
                row.registered_at = (
                    record.registered_at.isoformat() if record.registered_at else None
                )
                row.last_seen = record.last_seen.isoformat() if record.last_seen else None
                row.lat = record.lat
                row.lon = record.lon
                row.last_ip = record.last_ip
                row.battery_pct = record.battery_pct
                row.cpu_pct = record.cpu_pct
                row.ram_pct = record.ram_pct
                session.commit()
        except Exception as exc:
            logger.error("❌ [C2] _save_to_db falhou para '%s': %s", record.soldier_id, exc)

    def _load_from_db(self) -> int:
        """Load ONLINE/RECONNECTING Soldiers from SQLite into the in-memory registry.

        Returns:
            Number of soldiers loaded.
        """
        if self._engine is None or not _SQLMODEL_AVAILABLE:
            return 0
        loaded = 0
        try:
            active_statuses = [SoldierStatus.ONLINE.value, SoldierStatus.RECONNECTING.value]
            with Session(self._engine) as session:
                # Filter at DB level for efficiency
                stmt = select(SoldierDB).where(
                    SoldierDB.status.in_(active_statuses)  # type: ignore[union-attr]
                )
                rows = session.exec(stmt).all()
                for row in rows:
                    try:
                        status = SoldierStatus(row.status)
                    except ValueError:
                        status = SoldierStatus.OFFLINE
                    record = SoldierRecord(
                        soldier_id=row.soldier_id,
                        public_key=row.public_key,
                        device_type=row.device_type,
                        alias=row.alias,
                        status=status,
                        registered_at=(
                            datetime.fromisoformat(row.registered_at)
                            if row.registered_at
                            else datetime.now(timezone.utc)
                        ),
                        last_seen=(
                            datetime.fromisoformat(row.last_seen) if row.last_seen else None
                        ),
                        lat=row.lat,
                        lon=row.lon,
                        last_ip=row.last_ip,
                        battery_pct=row.battery_pct,
                        cpu_pct=row.cpu_pct,
                        ram_pct=row.ram_pct,
                    )
                    self._registry[record.soldier_id] = record
                    loaded += 1
        except Exception as exc:
            logger.error("❌ [C2] _load_from_db falhou: %s", exc)
        return loaded

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
