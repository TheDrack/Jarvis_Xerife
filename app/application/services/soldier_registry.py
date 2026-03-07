# -*- coding: utf-8 -*-
"""Soldier Registry — centralised directory of available edge devices.

Tracks all connected soldiers (devices), their capabilities and online
status.  Persists registrations in Supabase (when configured) and keeps an
in-memory copy for fast synchronous queries.

Usage::

    registry = get_soldier_registry()
    registry.register("raspi-01", ["gpio", "camera"])
    soldiers = registry.get_available_soldiers("camera")
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class SoldierRegistry(NexusComponent):
    """Directory of known edge devices and their capabilities.

    Memory is the authoritative store.  Supabase is used as a secondary
    persistence layer (best-effort: failures never interrupt operation).
    """

    def __init__(self) -> None:
        # {soldier_id: {device_type, capabilities, status, registered_at, last_seen}}
        self._registry: Dict[str, Dict[str, Any]] = {}

    def execute(self, context: dict) -> dict:
        """NexusComponent entry-point: returns registry snapshot."""
        return {"success": True, "soldiers": self.list_all()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        soldier_id: str,
        capabilities: List[str],
        device_type: str = "unknown",
    ) -> Dict[str, Any]:
        """Register (or update) a soldier in the directory.

        Args:
            soldier_id:   Unique device identifier.
            capabilities: List of capability tags (e.g. ``["pyautogui", "gpio"]``).
            device_type:  Human-readable device category.

        Returns:
            The stored soldier record.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        existing = self._registry.get(soldier_id, {})
        record: Dict[str, Any] = {
            "soldier_id": soldier_id,
            "device_type": device_type,
            "capabilities": list(capabilities),
            "status": "online",
            "registered_at": existing.get("registered_at", now),
            "last_seen": now,
        }
        self._registry[soldier_id] = record
        logger.info("🪖 [SoldierRegistry] Registered: %s (caps=%s)", soldier_id, capabilities)

        # Persist to Supabase (best-effort)
        self._persist(record)
        return record

    def unregister(self, soldier_id: str) -> bool:
        """Mark a soldier as offline (keeps the record for audit).

        Args:
            soldier_id: The device to unregister.

        Returns:
            ``True`` if the soldier was found and updated, ``False`` otherwise.
        """
        if soldier_id not in self._registry:
            return False
        self._registry[soldier_id]["status"] = "offline"
        self._registry[soldier_id]["last_seen"] = datetime.now(tz=timezone.utc).isoformat()
        logger.info("🪖 [SoldierRegistry] Unregistered: %s", soldier_id)
        self._persist(self._registry[soldier_id])
        return True

    def get_available_soldiers(self, capability: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return online soldiers, optionally filtered by *capability*.

        Args:
            capability: Capability tag to filter by.  When ``None`` all online
                        soldiers are returned.

        Returns:
            List of soldier records.
        """
        results = [
            rec
            for rec in self._registry.values()
            if rec.get("status") == "online"
        ]
        if capability:
            results = [r for r in results if capability in r.get("capabilities", [])]
        return results

    def get_soldier(self, soldier_id: str) -> Optional[Dict[str, Any]]:
        """Look up a soldier by ID.

        Args:
            soldier_id: The device identifier.

        Returns:
            Soldier record or ``None``.
        """
        return self._registry.get(soldier_id)

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all known soldiers (online and offline)."""
        return list(self._registry.values())

    # ------------------------------------------------------------------
    # Supabase persistence (best-effort)
    # ------------------------------------------------------------------

    def _persist(self, record: Dict[str, Any]) -> None:
        """Upsert *record* to the ``soldiers`` Supabase table."""
        try:
            from app.adapters.infrastructure.supabase_client import get_supabase_client

            client = get_supabase_client()
            if client is None:
                return
            # Map to DB schema (DeviceOrchestratorService uses same table)
            row = {
                "soldier_id": record["soldier_id"],
                "device_type": record.get("device_type", "unknown"),
                "status": record.get("status", "offline"),
                "last_seen": record.get("last_seen"),
            }
            client.table("soldiers").upsert(row).execute()
        except Exception as exc:
            logger.debug("[SoldierRegistry] Supabase persist falhou: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[SoldierRegistry] = None


def get_soldier_registry() -> SoldierRegistry:
    """Return the global :class:`SoldierRegistry` singleton."""
    global _registry
    if _registry is None:
        _registry = SoldierRegistry()
    return _registry
