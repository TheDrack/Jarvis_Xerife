"""Authenticated API for shared multi-agent task scheduling."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from app.adapters.infrastructure.agent_worker_credentials import AgentWorkerCredentialStore
from app.application.services.agent_task_queue_service import (
    AgentTaskQueueService, TaskQueueUnavailable,
)
from app.core.nexus import nexus

logger = logging.getLogger(__name__)


def _emit_proactive_task_signal(
    owner_id: str | None,
    event_type: str,
    *,
    task_id: str,
    result: dict[str, Any],
) -> bool:
    """Forward a grounded task event using only the authenticated owner's identity."""
    owner_id = str(owner_id or "").strip()
    if not owner_id or event_type != "task_blocked":
        return False

    assistant = nexus.resolve("assistant_service")
    handler = getattr(assistant, "on_event", None) if assistant is not None else None
    if not callable(handler):
        return False

    details = result if isinstance(result, dict) else {}
    payload = {
        "user_id": owner_id,
        "title": str(details.get("title") or f"Tarefa bloqueada: {task_id}")[:180],
        "objective": str(details.get("objective") or details.get("description") or "")[:500],
        "evidence_ref": f"agent-task:{task_id}"[:200],
        "confidence": 0.95,
        "impact": 0.75,
        "urgency": 0.75,
        "availability": 0.9,
        "interruption_cost": 0.15,
    }
    try:
        handler(event_type, payload)
        return True
    except Exception as exc:
        logger.warning("Could not forward proactive task signal (%s)", type(exc).__name__)
        return False


class AgentHeartbeatRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=200)
    runtime_version: str = "unknown"
    environment: str = "unknown"
    model_provider: str = "unknown"
    available_tools: list[str] = Field(default_factory=list)
    status: str = "available"
    concurrency_limit: int = Field(default=1, ge=1, le=64)
    estimated_cost: float = Field(default=0, ge=0)
    coordination_cost: float = Field(default=0, ge=0)
    estimated_latency_seconds: float = Field(default=0, ge=0)


class EnqueueTaskRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=10000)
    priority: int = Field(default=50, ge=0, le=1000)
    task_type: str = "general"
    required_tools: list[str] = Field(default_factory=list)
    constraints: list[Any] = Field(default_factory=list)
    acceptance_criteria: list[Any] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    leader_id: str = "jarvis"
    parent_task_id: str | None = None
    routine_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=250)
    max_attempts: int = Field(default=3, ge=1, le=20)
    expected_value: float = Field(default=1, ge=0)
    max_cost: float | None = Field(default=None, ge=0)


class ClaimTaskRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=200)
    lease_seconds: int = Field(default=90, ge=10, le=3600)


class FinishTaskRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=200)
    attempt_id: str
    status: Literal["completed", "failed", "blocked", "cancelled", "recovery_pending", "approval_required"]
    result: dict[str, Any] = Field(default_factory=dict)


class ReleaseTaskRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=200)
    attempt_id: str
    reason: str = Field(default="worker error", max_length=500)


class TriggerRoutineRequest(BaseModel):
    run_key: str = Field(min_length=1, max_length=250)


class RoutineRequest(BaseModel):
    routine_key: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=500)
    priority: int = Field(default=50, ge=0, le=1000)
    schedule: dict[str, Any] = Field(default_factory=dict)
    task_template: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


def create_agent_tasks_router(db_adapter, get_current_user, get_current_worker=None) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["agent-task-queue"])

    @lru_cache(maxsize=1)
    def queue_engine():
        # Prefer an explicit shared PostgreSQL URL. The general history adapter
        # may use local SQLite, which is not a shared multi-agent queue.
        database_url = os.getenv("JARVIS_TASK_QUEUE_DATABASE_URL") or os.getenv("DATABASE_URL")
        if database_url:
            if database_url.startswith("postgres://"):
                database_url = "postgresql://" + database_url[len("postgres://"):]
            return create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
        engine = getattr(db_adapter, "engine", None) if db_adapter else None
        if engine is not None and engine.dialect.name == "postgresql":
            return engine
        return None

    def service() -> AgentTaskQueueService:
        engine = queue_engine()
        if engine is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Shared task queue requires JARVIS_TASK_QUEUE_DATABASE_URL or "
                    "DATABASE_URL pointing to the PostgreSQL database with the Jarvis "
                    "multi-agent migrations applied."
                ),
            )
        return AgentTaskQueueService(engine)

    def authenticated_owner_id(user: Any) -> str:
        def identity_field(name: str):
            if isinstance(user, dict):
                return user.get(name)
            return getattr(user, name, None)

        value = identity_field("user_id") or identity_field("id")
        # AuthAdapter's environment-admin fallback deliberately has no database
        # user ID. Give that single local principal a stable, non-user-editable key.
        if not value and identity_field("username") == "admin":
            value = "local-admin"
        owner_id = str(value or "").strip()
        if not owner_id or len(owner_id) > 200:
            raise HTTPException(
                status_code=401,
                detail="Authenticated user has no stable owner identity",
            )
        return owner_id

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, TaskQueueUnavailable):
            return HTTPException(status_code=503, detail=str(exc))
        if isinstance(exc, PermissionError):
            return HTTPException(status_code=403, detail=str(exc))
        if isinstance(exc, IntegrityError):
            return HTTPException(status_code=409, detail="Task or routine identifier already exists")
        if isinstance(exc, ValueError):
            return HTTPException(status_code=422, detail=str(exc))
        return HTTPException(status_code=500, detail="Task queue operation failed")

    def authenticate_worker(
        worker_token: str | None = Header(default=None, alias="X-Jarvis-Worker-Token"),
    ):
        if not isinstance(worker_token, str) or not worker_token.strip():
            raise HTTPException(
                status_code=401,
                detail="Worker credential is required",
                headers={"WWW-Authenticate": "JarvisWorker"},
            )
        engine = queue_engine()
        if engine is None or getattr(getattr(engine, "dialect", None), "name", None) != "postgresql":
            raise HTTPException(
                status_code=503,
                detail="Worker credential registry requires the shared PostgreSQL task queue",
            )
        try:
            principal = AgentWorkerCredentialStore(engine).authenticate(worker_token.strip())
        except Exception as exc:
            logger.error("Worker credential lookup failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="Worker credential registry is unavailable",
            ) from None
        if principal is None:
            raise HTTPException(
                status_code=401,
                detail="Worker credential is invalid, expired, or revoked",
                headers={"WWW-Authenticate": "JarvisWorker"},
            )
        return principal

    worker_dependency = get_current_worker or authenticate_worker

    def require_worker_identity(requested_agent_id: str, principal: Any) -> str:
        trusted_agent_id = str(getattr(principal, "agent_id", "") or "").strip()
        if not trusted_agent_id or requested_agent_id != trusted_agent_id:
            raise HTTPException(status_code=403, detail="Worker credential is not authorized for this agent")
        return trusted_agent_id

    @router.post("/agents/heartbeat")
    async def heartbeat(
        request: AgentHeartbeatRequest,
        _user=Depends(get_current_user),
        worker=Depends(worker_dependency),
    ):
        try:
            agent_id = require_worker_identity(request.agent_id, worker)
            payload = request.model_dump(exclude={"agent_id", "available_tools"})
            payload["agent_id"] = agent_id
            payload["available_tools"] = list(worker.available_tools)
            # The current worker runtime executes one task per loop. Do not let
            # the request body inflate the scheduler's concurrency budget.
            payload["concurrency_limit"] = 1
            return service().heartbeat(**payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks")
    async def enqueue(request: EnqueueTaskRequest, _user=Depends(get_current_user)):
        try:
            owner_id = authenticated_owner_id(_user)
            payload = request.model_dump()
            payload["created_by"] = owner_id
            payload["owner_id"] = owner_id
            return service().enqueue(**payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks/claim-next")
    async def claim_next(
        request: ClaimTaskRequest,
        _user=Depends(get_current_user),
        worker=Depends(worker_dependency),
    ):
        try:
            agent_id = require_worker_identity(request.agent_id, worker)
            task = service().claim_next(agent_id, request.lease_seconds)
            return {"task": task}
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks/{task_id}/finish")
    async def finish(
        task_id: str,
        request: FinishTaskRequest,
        _user=Depends(get_current_user),
        worker=Depends(worker_dependency),
    ):
        try:
            agent_id = require_worker_identity(request.agent_id, worker)
            queue = service()
            accepted = queue.finish(
                task_id, agent_id, request.attempt_id, request.status, request.result
            )
            if not accepted:
                raise HTTPException(status_code=409, detail="Task ownership or attempt is stale")
            if request.status == "blocked":
                try:
                    task_owner = queue.get_task_owner(task_id)
                except Exception as exc:
                    logger.warning(
                        "Could not resolve task owner for proactive signal (%s)",
                        type(exc).__name__,
                    )
                else:
                    _emit_proactive_task_signal(
                        task_owner,
                        "task_blocked",
                        task_id=task_id,
                        result=request.result,
                    )
            return {"accepted": True, "task_id": task_id, "status": request.status}
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks/{task_id}/release")
    async def release(
        task_id: str,
        request: ReleaseTaskRequest,
        _user=Depends(get_current_user),
        worker=Depends(worker_dependency),
    ):
        try:
            agent_id = require_worker_identity(request.agent_id, worker)
            released = service().release(
                task_id, agent_id, request.attempt_id, request.reason
            )
            if not released:
                raise HTTPException(status_code=409, detail="Task ownership or attempt is stale")
            return {"released": True, "task_id": task_id}
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/routines")
    async def upsert_routine(request: RoutineRequest, _user=Depends(get_current_user)):
        try:
            owner_id = authenticated_owner_id(_user)
            payload = request.model_dump()
            payload["created_by"] = owner_id
            payload["owner_id"] = owner_id
            return service().create_routine(**payload)
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/routines/{routine_key}/trigger")
    async def trigger_routine(
        routine_key: str,
        request: TriggerRoutineRequest,
        _user=Depends(get_current_user),
    ):
        try:
            owner_id = authenticated_owner_id(_user)
            return service().trigger_routine(
                routine_key,
                request.run_key,
                owner_id=owner_id,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    return router
