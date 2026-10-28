"""Authenticated API for shared multi-agent task scheduling."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine

from app.application.services.agent_task_queue_service import (
    AgentTaskQueueService, TaskQueueUnavailable,
)


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


def create_agent_tasks_router(db_adapter, get_current_user) -> APIRouter:
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

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, TaskQueueUnavailable):
            return HTTPException(status_code=503, detail=str(exc))
        if isinstance(exc, ValueError):
            return HTTPException(status_code=422, detail=str(exc))
        return HTTPException(status_code=500, detail="Task queue operation failed")

    @router.post("/agents/heartbeat")
    async def heartbeat(request: AgentHeartbeatRequest, _user=Depends(get_current_user)):
        try:
            return service().heartbeat(**request.model_dump())
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks")
    async def enqueue(request: EnqueueTaskRequest, _user=Depends(get_current_user)):
        try:
            return service().enqueue(**request.model_dump())
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks/claim-next")
    async def claim_next(request: ClaimTaskRequest, _user=Depends(get_current_user)):
        try:
            task = service().claim_next(request.agent_id, request.lease_seconds)
            return {"task": task}
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks/{task_id}/finish")
    async def finish(task_id: str, request: FinishTaskRequest, _user=Depends(get_current_user)):
        try:
            accepted = service().finish(
                task_id, request.agent_id, request.attempt_id, request.status, request.result
            )
            if not accepted:
                raise HTTPException(status_code=409, detail="Task ownership or attempt is stale")
            return {"accepted": True, "task_id": task_id, "status": request.status}
        except HTTPException:
            raise
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/agent-tasks/{task_id}/release")
    async def release(task_id: str, request: ReleaseTaskRequest, _user=Depends(get_current_user)):
        try:
            released = service().release(
                task_id, request.agent_id, request.attempt_id, request.reason
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
            return service().create_routine(**request.model_dump())
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/routines/{routine_key}/trigger")
    async def trigger_routine(
        routine_key: str,
        request: TriggerRoutineRequest,
        _user=Depends(get_current_user),
    ):
        try:
            return service().trigger_routine(routine_key, request.run_key)
        except Exception as exc:
            raise translate_error(exc) from exc

    return router
