"""Authenticated passive local-network discovery endpoint."""
from fastapi import APIRouter, Depends

from app.adapters.infrastructure.api_models import User
from app.application.services.network_discovery_service import discover_passive_neighbors


def create_network_discovery_router(get_current_user) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/network/discovery")
    async def discover_network(current_user: User = Depends(get_current_user)):
        """Read only the local ARP neighbor cache; never probes the network."""
        return discover_passive_neighbors()

    return router
