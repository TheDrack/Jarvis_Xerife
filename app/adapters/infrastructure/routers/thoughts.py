# -*- coding: utf-8 -*-
"""Thoughts router: /v1/thoughts/* endpoints for ThoughtLog (self-healing orchestrator)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.infrastructure import api_models
from app.adapters.infrastructure.api_models import User

logger = logging.getLogger(__name__)


def _thought_to_response(t) -> api_models.ThoughtLogResponse:
    """Convert a ThoughtLog ORM object to a ThoughtLogResponse."""
    return api_models.ThoughtLogResponse(
        id=t.id,
        mission_id=t.mission_id,
        session_id=t.session_id,
        status=t.status,
        thought_process=t.thought_process,
        problem_description=t.problem_description,
        solution_attempt=t.solution_attempt,
        success=t.success,
        error_message=t.error_message,
        retry_count=t.retry_count,
        requires_human=t.requires_human,
        escalation_reason=t.escalation_reason,
        created_at=t.created_at.isoformat(),
    )


def create_thoughts_router(db_adapter, get_current_user) -> APIRouter:
    """
    Create the thoughts router.

    Args:
        db_adapter: SQLiteHistoryAdapter whose engine is shared with ThoughtLogService
        get_current_user: Dependency callable for authentication

    Returns:
        Configured APIRouter
    """
    from app.application.services.thought_log_service import ThoughtLogService

    thought_log_service = ThoughtLogService(engine=db_adapter.engine)
    router = APIRouter()

    @router.post("/v1/thoughts", response_model=api_models.ThoughtLogResponse)
    async def create_thought_log(
        request: api_models.ThoughtLogRequest,
        current_user: User = Depends(get_current_user),
    ) -> api_models.ThoughtLogResponse:
        """Create a thought log entry (Protected endpoint)."""
        try:
            from app.domain.models.thought_log import InteractionStatus

            logger.info(
                f"User '{current_user.username}' creating thought log for mission {request.mission_id}"
            )
            thought = thought_log_service.create_thought(
                mission_id=request.mission_id,
                session_id=request.session_id,
                thought_process=request.thought_process,
                problem_description=request.problem_description,
                solution_attempt=request.solution_attempt,
                status=InteractionStatus(request.status),
                success=request.success,
                error_message=request.error_message,
                context_data=request.context_data,
            )
            if thought:
                return _thought_to_response(thought)
            raise HTTPException(status_code=500, detail="Failed to create thought log")
        except Exception as e:
            logger.error(f"Error creating thought log: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create thought log: {str(e)}")

    @router.get(
        "/v1/thoughts/mission/{mission_id}", response_model=api_models.ThoughtLogListResponse
    )
    async def get_mission_thoughts(
        mission_id: str,
        current_user: User = Depends(get_current_user),
    ) -> api_models.ThoughtLogListResponse:
        """Get all thought logs for a specific mission (Protected endpoint)."""
        try:
            logger.info(f"User '{current_user.username}' fetching thoughts for mission {mission_id}")
            thoughts = thought_log_service.get_mission_thoughts(mission_id)
            responses = [_thought_to_response(t) for t in thoughts]
            return api_models.ThoughtLogListResponse(logs=responses, total=len(responses))
        except Exception as e:
            logger.error(f"Error fetching mission thoughts: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to fetch thoughts: {str(e)}")

    @router.get(
        "/v1/thoughts/escalations", response_model=api_models.ThoughtLogListResponse
    )
    async def get_pending_escalations(
        current_user: User = Depends(get_current_user),
    ) -> api_models.ThoughtLogListResponse:
        """Get all missions requiring human intervention (Protected endpoint)."""
        try:
            logger.info(f"User '{current_user.username}' fetching pending escalations")
            escalations = thought_log_service.get_pending_escalations()
            responses = [_thought_to_response(t) for t in escalations]
            return api_models.ThoughtLogListResponse(logs=responses, total=len(responses))
        except Exception as e:
            logger.error(f"Error fetching escalations: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to fetch escalations: {str(e)}")

    @router.get("/v1/thoughts/mission/{mission_id}/consolidated")
    async def get_consolidated_log(
        mission_id: str,
        current_user: User = Depends(get_current_user),
    ) -> dict:
        """Get consolidated log for a mission (Protected endpoint)."""
        try:
            logger.info(
                f"User '{current_user.username}' fetching consolidated log for {mission_id}"
            )
            consolidated = thought_log_service.generate_consolidated_log(mission_id)
            return {"mission_id": mission_id, "consolidated_log": consolidated}
        except Exception as e:
            logger.error(f"Error generating consolidated log: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to generate log: {str(e)}")

    return router
