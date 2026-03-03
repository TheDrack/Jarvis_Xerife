# -*- coding: utf-8 -*-
"""GitHub router: /v1/github/*, /v1/jarvis/dispatch endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.infrastructure import api_models
from app.adapters.infrastructure.api_models import (
    JarvisDispatchRequest,
    JarvisDispatchResponse,
    User,
)

logger = logging.getLogger(__name__)


def create_github_router(db_adapter, get_current_user) -> APIRouter:
    """
    Create the GitHub and dispatch router.

    Args:
        db_adapter: SQLiteHistoryAdapter whose engine is shared with ThoughtLogService
        get_current_user: Dependency callable for authentication

    Returns:
        Configured APIRouter
    """
    from app.application.services.github_worker import GitHubWorker
    from app.application.services.thought_log_service import ThoughtLogService

    github_worker = GitHubWorker()
    thought_log_service = ThoughtLogService(engine=db_adapter.engine)
    router = APIRouter()

    @router.post("/v1/github/worker", response_model=api_models.GitHubWorkerResponse)
    async def github_worker_operation(
        request: api_models.GitHubWorkerRequest,
        current_user: User = Depends(get_current_user),
    ) -> api_models.GitHubWorkerResponse:
        """Execute GitHub worker operations (Protected endpoint)."""
        try:
            logger.info(
                f"User '{current_user.username}' executing GitHub operation: {request.operation}"
            )

            if request.operation == "create_branch":
                if not request.branch_name:
                    raise HTTPException(status_code=400, detail="branch_name is required")
                result = github_worker.create_feature_branch(request.branch_name)

            elif request.operation == "submit_pr":
                if not request.pr_title:
                    raise HTTPException(status_code=400, detail="pr_title is required")
                result = github_worker.submit_pull_request(
                    title=request.pr_title,
                    body=request.pr_body or "",
                )

            elif request.operation == "fetch_ci_status":
                result = github_worker.fetch_ci_status(run_id=request.run_id)

            else:
                raise HTTPException(
                    status_code=400, detail=f"Unknown operation: {request.operation}"
                )

            return api_models.GitHubWorkerResponse(
                success=result.get("success", False),
                message=result.get("message", ""),
                data=result,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error executing GitHub operation: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"GitHub operation failed: {str(e)}")

    @router.post("/v1/github/ci-heal/{run_id}")
    async def auto_heal_ci_failure(
        run_id: int,
        mission_id: str,
        current_user: User = Depends(get_current_user),
    ) -> dict:
        """Automatically attempt to heal a CI failure (Protected endpoint)."""
        try:
            logger.info(
                f"User '{current_user.username}' initiating auto-heal for CI run {run_id}"
            )
            result = github_worker.auto_heal_ci_failure(
                run_id=run_id,
                mission_id=mission_id,
                thought_log_service=thought_log_service,
            )
            return result
        except Exception as e:
            logger.error(f"Error in auto-heal: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Auto-heal failed: {str(e)}")

    @router.post("/v1/jarvis/dispatch", response_model=JarvisDispatchResponse)
    async def jarvis_dispatch(
        request: JarvisDispatchRequest,
        current_user: User = Depends(get_current_user),
    ) -> JarvisDispatchResponse:
        """
        Trigger a repository_dispatch event for Jarvis Self-Healing (Protected endpoint).

        Use this endpoint for automatic code fixes/creation via GitHub Agents.
        NOT for manual issue tracking – use GitHub Issues for that instead.
        """
        try:
            logger.info(
                f"User '{current_user.username}' triggering Jarvis dispatch: "
                f"intent='{request.intent}', instruction='{request.instruction[:100]}...'"
            )
            client_payload = {
                "intent": request.intent,
                "instruction": request.instruction,
                "context": request.context or "",
                "triggered_by": current_user.username,
            }
            result = github_worker.trigger_repository_dispatch(
                event_type="jarvis_order",
                client_payload=client_payload,
            )
            if result.get("success"):
                return JarvisDispatchResponse(
                    success=True,
                    message=result.get("message", "Dispatch triggered successfully"),
                    workflow_url=result.get("workflow_url"),
                )
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to trigger dispatch"),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error triggering Jarvis dispatch: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Dispatch failed: {str(e)}")

    return router
