# -*- coding: utf-8 -*-
"""Soldier Provider Port - Interface for Authorized Soldier registry operations."""

from abc import abstractmethod
from typing import Dict, List, Optional

from app.core.nexuscomponent import NexusComponent
from app.domain.models.soldier import SoldierRecord, SoldierRegistration, SoldierStatus


class SoldierProvider(NexusComponent):
    """
    Port (interface) for the Authorized Soldier C2 registry.

    Implementations must manage the lifecycle of Soldier devices, including
    registration, status updates, and tactical-map queries.
    """

    def execute(self, context: Optional[Dict] = None) -> Dict:
        """NexusComponent entry point — defaults to listing active soldiers."""
        return {"success": False, "not_implemented": True}

    @abstractmethod
    def register_soldier(self, registration: SoldierRegistration) -> SoldierRecord:
        """
        Register a new Soldier or update an existing one.

        Args:
            registration: Validated registration payload.

        Returns:
            The persisted SoldierRecord.
        """

    @abstractmethod
    def get_soldier(self, soldier_id: str) -> Optional[SoldierRecord]:
        """
        Retrieve a Soldier by its unique ID.

        Returns:
            The SoldierRecord, or None if not found.
        """

    @abstractmethod
    def update_status(self, soldier_id: str, status: SoldierStatus) -> bool:
        """
        Update the online/offline status of a Soldier.

        Returns:
            True if the update succeeded, False otherwise.
        """

    @abstractmethod
    def list_soldiers(self, status_filter: Optional[SoldierStatus] = None) -> List[SoldierRecord]:
        """
        List all registered Soldiers, optionally filtered by status.

        Args:
            status_filter: If provided, only return soldiers with this status.

        Returns:
            Ordered list of SoldierRecords.
        """

    @abstractmethod
    def deregister_soldier(self, soldier_id: str) -> bool:
        """
        Remove a Soldier from the registry.

        Returns:
            True if the soldier existed and was removed, False otherwise.
        """
