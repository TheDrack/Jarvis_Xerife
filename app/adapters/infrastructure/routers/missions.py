# -*- coding: utf-8 -*-
"""Missions router: /v1/missions/*, /v1/browser/* endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.adapters.infrastructure import api_models
from app.adapters.infrastructure.api_models import User

logger = logging.getLogger(__name__)


def create_missions_router(get_current_user) -> APIRouter:
    """
    Create the missions and browser router.

    Args:
        get_current_user: Dependency callable for authentication

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/v1/missions/execute", response_model=api_models.MissionResponse)
    async def execute_mission(
        request: api_models.MissionRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> api_models.MissionResponse:
        """Execute a serverless task mission in an isolated environment (Protected endpoint)."""
        try:
            from app.application.services.task_runner import TaskRunner
            from app.domain.models.mission import Mission

            logger.info(f"User '{current_user.username}' executing mission: {request.mission_id}")

            mission = Mission(
                mission_id=request.mission_id,
                code=request.code,
                requirements=request.requirements,
                browser_interaction=request.browser_interaction,
                keep_alive=request.keep_alive,
                target_device_id=request.target_device_id,
                timeout=request.timeout,
                metadata=request.metadata,
            )
            result = TaskRunner().execute_mission(mission)

            return api_models.MissionResponse(
                mission_id=result.mission_id,
                success=result.success,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                execution_time=result.execution_time,
                error=result.error,
                metadata=result.metadata,
            )
        except Exception as e:
            logger.error(f"Error executing mission: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Mission execution failed: {str(e)}")

    @router.post("/v1/browser/control", response_model=api_models.BrowserControlResponse)
    async def control_browser(
        request: api_models.BrowserControlRequest,
        current_user: User = Depends(get_current_user),
    ) -> api_models.BrowserControlResponse:
        """Control the persistent browser instance (Protected endpoint)."""
        try:
            from app.application.services.browser_manager import PersistentBrowserManager

            logger.info(f"User '{current_user.username}' browser operation: {request.operation}")
            browser_manager = PersistentBrowserManager()

            if request.operation == "start":
                cdp_url = browser_manager.start_browser(port=request.port)
                return api_models.BrowserControlResponse(
                    success=bool(cdp_url),
                    is_running=bool(cdp_url),
                    cdp_url=cdp_url,
                    message="Browser started successfully" if cdp_url else "Failed to start browser",
                )
            elif request.operation == "stop":
                success = browser_manager.stop_browser()
                return api_models.BrowserControlResponse(
                    success=success,
                    is_running=browser_manager.is_running(),
                    cdp_url=None,
                    message="Browser stopped" if success else "Failed to stop browser",
                )
            elif request.operation == "status":
                is_running = browser_manager.is_running()
                cdp_url = browser_manager.get_cdp_url() if is_running else None
                return api_models.BrowserControlResponse(
                    success=True,
                    is_running=is_running,
                    cdp_url=cdp_url,
                    message="Browser is running" if is_running else "Browser is not running",
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid operation: {request.operation}. Must be 'start', 'stop', or 'status'",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error controlling browser: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Browser control failed: {str(e)}")

    @router.post("/v1/browser/record", response_model=api_models.RecordAutomationResponse)
    async def record_automation(
        request: api_models.RecordAutomationRequest,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
    ) -> api_models.RecordAutomationResponse:
        """
        Start recording browser automation with Playwright codegen (Protected endpoint).

        Generates Python automation code from recorded browser interactions.
        """
        try:
            from app.application.services.browser_manager import PersistentBrowserManager

            logger.info(f"User '{current_user.username}' starting automation recording")
            browser_manager = PersistentBrowserManager()
            output_file = Path(request.output_file) if request.output_file else None
            output_path = browser_manager.record_automation(output_file=output_file)

            if output_path:
                return api_models.RecordAutomationResponse(
                    success=True,
                    output_file=output_path,
                    message="Recording started. Close the browser when done to save the generated code.",
                )
            return api_models.RecordAutomationResponse(
                success=False,
                output_file=None,
                message="Failed to start recording. Make sure Playwright is installed.",
            )
        except Exception as e:
            logger.error(f"Error starting automation recording: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Recording failed: {str(e)}")

    return router
