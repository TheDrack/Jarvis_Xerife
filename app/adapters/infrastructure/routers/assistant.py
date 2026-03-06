# -*- coding: utf-8 -*-
"""Assistant router: /v1/execute, /v1/message, /v1/task, /v1/status, /v1/history"""

import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from app.adapters.infrastructure.api_models import (
    CommandHistoryItem,
    ExecuteRequest,
    ExecuteResponse,
    HistoryResponse,
    MessageRequest,
    MessageResponse,
    StatusResponse,
    TaskResponse,
    User,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def _ws_notify(user: User, event_type: str, data: Dict[str, Any]) -> None:
    """Fire-and-forget WebSocket notification to the user's HUD."""
    try:
        from app.adapters.infrastructure.websocket_manager import get_websocket_manager

        manager = get_websocket_manager()
        user_id = getattr(user, "user_id", None) or getattr(user, "username", "")
        if not user_id or not manager.is_connected(user_id):
            return
        payload = {"type": event_type, "data": data}
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(manager.broadcast_to_user(user_id, payload))
        else:
            loop.run_until_complete(manager.broadcast_to_user(user_id, payload))
    except Exception as exc:
        logger.debug("[assistant] _ws_notify falhou silenciosamente: %s", exc)


def create_assistant_router(assistant_service, db_adapter, get_current_user, limiter=None) -> APIRouter:
    """
    Create the assistant router with all command/message endpoints.

    Args:
        assistant_service: Injected AssistantService instance
        db_adapter: SQLiteHistoryAdapter for task persistence
        get_current_user: Dependency callable for authentication
        limiter: Optional slowapi Limiter instance for rate limiting

    Returns:
        Configured APIRouter
    """
    from app.adapters.infrastructure.api_models import RequestSource

    router = APIRouter()

    def _noop_decorator(f):
        """No-op decorator used when rate limiting is disabled."""
        return f

    _rate_limit = limiter.limit("30/minute") if limiter is not None else _noop_decorator

    def _should_bypass_identifier(request_source: str = None) -> bool:
        """Return True if request should skip Jarvis intent identification."""
        if not request_source:
            return False
        return request_source in {
            RequestSource.GITHUB_ACTIONS.value,
            RequestSource.GITHUB_ISSUE.value,
        }

    @router.post("/v1/execute", response_model=ExecuteResponse)
    @_rate_limit
    async def execute_command(
        request: Request,
        body: ExecuteRequest,
        current_user: User = Depends(get_current_user),
    ) -> ExecuteResponse:
        """
        Execute a command and return the result (Protected endpoint).

        Supports intelligent routing based on request source:
        - GitHub Actions/Issues: Bypass Jarvis identifier, process directly with AI
        - User API requests: Use Jarvis intent identification
        """
        try:
            request_source = None
            if body.metadata and body.metadata.request_source:
                request_source = body.metadata.request_source.value

            source_info = f" (source: {request_source})" if request_source else ""
            logger.info(
                f"User '{current_user.username}' executing command via API{source_info}: {body.command}"
            )

            bypass_identifier = _should_bypass_identifier(request_source)
            if bypass_identifier:
                logger.info("GitHub-sourced request – bypassing Jarvis identifier.")

            metadata_dict = None
            if body.metadata:
                metadata_dict = {
                    "source_device_id": body.metadata.source_device_id,
                    "network_id": body.metadata.network_id,
                    "network_type": body.metadata.network_type,
                    "request_source": request_source,
                    "bypass_identifier": bypass_identifier,
                }

            response = await assistant_service.async_process_command(
                body.command, channel="api", request_metadata=metadata_dict
            )
            logger.info(
                f"Response for '{current_user.username}': success={response.success}, "
                f"len={len(response.message) if response.message else 0}"
            )
            result = ExecuteResponse(
                success=response.success,
                message=response.message,
                data=response.data,
                error=response.error,
            )
            # Push real-time status update to connected HUD (best-effort)
            _ws_notify(current_user, "execute_complete", result.model_dump())
            return result
        except Exception as e:
            logger.error(f"Error executing command: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @router.post("/v1/message", response_model=MessageResponse)
    @_rate_limit
    async def send_message(
        request: Request,
        body: MessageRequest,
        current_user: User = Depends(get_current_user),
    ) -> MessageResponse:
        """Send a natural-language message to the assistant (Protected endpoint)."""
        try:
            logger.info(f"User '{current_user.username}' sending message: {body.text}")
            response = await assistant_service.async_process_command(body.text, channel="api")
            logger.info(
                f"Response for '{current_user.username}': success={response.success}, "
                f"len={len(response.message) if response.message else 0}"
            )
            return MessageResponse(
                success=response.success,
                response=response.message,
                error=response.error,
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return MessageResponse(
                success=False,
                response="Erro ao processar mensagem. Tente novamente.",
                error=f"Internal server error: {str(e)}",
            )

    @router.post("/v1/task", response_model=TaskResponse)
    async def create_task(
        request: ExecuteRequest,
        current_user: User = Depends(get_current_user),
    ) -> TaskResponse:
        """
        Create a pending task for distributed execution (Protected endpoint).

        Saves the command to the database so the local worker can pick it up.
        """
        try:
            logger.info(f"User '{current_user.username}' creating task: {request.command}")
            intent = assistant_service.interpreter.interpret(request.command)
            task_id = db_adapter.save_pending_command(
                user_input=request.command,
                command_type=intent.command_type.value,
                parameters=intent.parameters,
            )
            if task_id is None:
                raise HTTPException(status_code=500, detail="Failed to create task in database")
            return TaskResponse(
                task_id=task_id,
                status="pending",
                message=f"Task created successfully with ID {task_id}",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @router.get("/v1/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        """Get the current system status."""
        try:
            return StatusResponse(
                app_name=settings.app_name,
                version=settings.version,
                is_active=assistant_service.is_running,
                wake_word=assistant_service.wake_word,
                language=settings.language,
            )
        except Exception as e:
            logger.error(f"Error getting status: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @router.get("/v1/history", response_model=HistoryResponse)
    async def get_history(limit: int = 5) -> HistoryResponse:
        """Get recent command history (max 50 entries)."""
        try:
            limit = max(1, min(limit, 50))
            history = assistant_service.get_command_history(limit=limit)
            return HistoryResponse(
                commands=[
                    CommandHistoryItem(
                        command=item["command"],
                        timestamp=item["timestamp"],
                        success=item["success"],
                        message=item["message"],
                    )
                    for item in history
                ],
                total=len(history),
            )
        except Exception as e:
            logger.error(f"Error getting history: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    return router
