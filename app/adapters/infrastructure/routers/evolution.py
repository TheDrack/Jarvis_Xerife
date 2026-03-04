# -*- coding: utf-8 -*-
"""Evolution router: /v1/status/evolution, /v1/evolution/* endpoints."""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.infrastructure import api_models

logger = logging.getLogger(__name__)


def create_evolution_router(db_adapter, get_current_user=None) -> APIRouter:
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

    # ------------------------------------------------------------------
    # Proposals / Strategist decision interface
    # ------------------------------------------------------------------

    def _get_strategist():
        from app.application.services.strategist_service import StrategistService

        return StrategistService()

    _auth_deps: List[Any] = [Depends(get_current_user)] if get_current_user else []

    @router.get(
        "/v1/proposals/pending",
        response_model=List[Dict[str, Any]],
        dependencies=_auth_deps,
    )
    async def list_pending_proposals() -> List[Dict[str, Any]]:
        """List all pending improvement proposals generated by StrategistService."""
        try:
            strategist = _get_strategist()
            pending_dir: Path = strategist.proposals_dir / "pending"
            if not pending_dir.exists():
                return []
            proposals: List[Dict[str, Any]] = []
            for proposal_file in sorted(pending_dir.glob("*.json")):
                try:
                    data: Dict[str, Any] = json.loads(proposal_file.read_text(encoding="utf-8"))
                    data["filename"] = proposal_file.name
                    proposals.append(data)
                except Exception as read_err:
                    logger.warning("⚠️ [PROPOSALS] Falha ao ler '%s': %s", proposal_file, read_err)
            logger.info("📋 [PROPOSALS] %d proposta(s) pendente(s) listada(s).", len(proposals))
            return proposals
        except Exception as e:
            logger.error("Error listing pending proposals: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to list proposals: {str(e)}")

    @router.post(
        "/v1/proposals/{proposal_id}/approve",
        response_model=Dict[str, Any],
        dependencies=_auth_deps,
    )
    async def approve_proposal(proposal_id: str) -> Dict[str, Any]:
        """Approve a pending proposal and trigger its implementation via GitHub dispatch."""
        try:
            strategist = _get_strategist()
            pending_dir: Path = strategist.proposals_dir / "pending"
            approved_dir: Path = strategist.approved_dir

            proposal_file = pending_dir / proposal_id
            if not proposal_file.exists():
                raise HTTPException(
                    status_code=404, detail=f"Proposal '{proposal_id}' not found in pending."
                )

            approved_dir.mkdir(parents=True, exist_ok=True)
            destination = approved_dir / proposal_id
            shutil.move(str(proposal_file), str(destination))
            logger.info("✅ [PROPOSALS] Proposta '%s' aprovada e movida.", proposal_id)

            from app.application.services.github_worker import GitHubWorker

            github_worker = GitHubWorker()
            dispatch_ok = github_worker.trigger_repository_dispatch(
                event_type="implement_proposal",
                client_payload={"proposal_id": proposal_id},
            )

            if not dispatch_ok:
                logger.warning(
                    "⚠️ [PROPOSALS] trigger_repository_dispatch falhou para '%s'.", proposal_id
                )

            return {
                "success": True,
                "proposal_id": proposal_id,
                "status": "approved",
                "dispatch_triggered": dispatch_ok,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error approving proposal '%s': %s", proposal_id, e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to approve proposal: {str(e)}")

    return router
