# -*- coding: utf-8 -*-
"""Evolution router: /v1/status/evolution, /v1/evolution/* endpoints."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.infrastructure import api_models

logger = logging.getLogger(__name__)


def create_evolution_router(db_adapter) -> APIRouter:
    """
    Create the evolution and self-awareness router.

    Args:
        db_adapter: SQLiteHistoryAdapter whose engine is passed to CapabilityManager

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    def _get_capability_manager():
        from app.application.services.capability_manager import CapabilityManager

        return CapabilityManager(engine=db_adapter.engine)

    @router.get("/v1/status/evolution", response_model=api_models.EvolutionStatusResponse)
    async def get_evolution_status() -> api_models.EvolutionStatusResponse:
        """
        Get JARVIS evolution status and chapter-by-chapter progress across 102 capabilities.
        """
        try:
            capability_manager = _get_capability_manager()
            progress = capability_manager.get_evolution_progress()
            return api_models.EvolutionStatusResponse(
                overall_progress=progress["overall_progress"],
                total_capabilities=progress["total_capabilities"],
                complete_capabilities=progress["complete_capabilities"],
                partial_capabilities=progress["partial_capabilities"],
                nonexistent_capabilities=progress["nonexistent_capabilities"],
                chapters=[api_models.ChapterProgress(**c) for c in progress["chapters"]],
            )
        except Exception as e:
            logger.error(f"Error getting evolution status: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to get evolution status: {str(e)}"
            )

    @router.get("/v1/evolution/next-step", response_model=api_models.NextEvolutionStepResponse)
    async def get_next_evolution_step() -> api_models.NextEvolutionStepResponse:
        """
        Get the next capability ready for implementation (self-evolution trigger).

        Raises 404 when all capabilities are complete or have missing resources.
        """
        try:
            capability_manager = _get_capability_manager()
            next_step = capability_manager.get_next_evolution_step()
            if next_step is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "No capabilities ready for implementation. "
                        "All capabilities either complete or have missing resources."
                    ),
                )
            blueprint_model = api_models.CapabilityRequirements(**next_step["blueprint"])
            return api_models.NextEvolutionStepResponse(
                capability_id=next_step["capability_id"],
                capability_name=next_step["capability_name"],
                chapter=next_step["chapter"],
                current_status=next_step["current_status"],
                blueprint=blueprint_model,
                priority_score=next_step["priority_score"],
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting next evolution step: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to get next evolution step: {str(e)}"
            )

    @router.post("/v1/evolution/scan", response_model=Dict[str, Any])
    async def scan_capabilities() -> Dict[str, Any]:
        """Scan the repository to detect implemented capabilities and update statuses."""
        try:
            return _get_capability_manager().status_scan()
        except Exception as e:
            logger.error(f"Error scanning capabilities: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to scan capabilities: {str(e)}"
            )

    @router.get(
        "/v1/evolution/requirements/{capability_id}",
        response_model=api_models.CapabilityRequirements,
    )
    async def get_capability_requirements(
        capability_id: int,
    ) -> api_models.CapabilityRequirements:
        """
        Get the technical requirements blueprint for a specific capability (1–102).
        """
        try:
            blueprint = _get_capability_manager().check_requirements(capability_id)
            if "error" in blueprint:
                raise HTTPException(status_code=404, detail=blueprint["error"])
            return api_models.CapabilityRequirements(**blueprint)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting capability requirements: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Failed to get requirements: {str(e)}"
            )

    return router
