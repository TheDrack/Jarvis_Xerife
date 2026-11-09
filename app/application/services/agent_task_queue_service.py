"""Priority-aware task queue for Jarvis multi-agent coordination.

The queue is backed by the PostgreSQL control-plane migration. It intentionally
uses database-side RPC functions for atomic claims instead of read-then-write
application logic.
"""
from __future__ import annotations

import json
import logging
import os
from threading import Lock
from typing import Any
from uuid import uuid4

from sqlalchemy import text

logger = logging.getLogger(__name__)


class TaskQueueUnavailable(RuntimeError):
    """Raised when the database does not support the Postgres task queue."""


class AgentTaskQueueService:
    def __init__(self, engine, decision_observer=None):
        self.engine = engine
        self._decision_observer = decision_observer
        self._decision_observer_lock = Lock()

    def _submit_laya_shadow(self, objective: str, task_type: str) -> None:
        """Observe queued task classification without changing queue data."""
        if self._decision_observer is None:
            if os.getenv("JARVIS_LAYA_SHADOW_ENABLED", "").strip().lower() != "true":
                return
            with self._decision_observer_lock:
                if self._decision_observer is None:
                    try:
                        from app.adapters.infrastructure.intelligence.laya_decision_adapter import (
                            LayaDecisionAdapter,
                        )
                        from app.application.services.laya_decision_shadow import (
                            LayaDecisionShadowObserver,
                        )
                        self._decision_observer = LayaDecisionShadowObserver(
                            LayaDecisionAdapter.from_env()
                        )
                    except Exception as exc:
                        logger.debug("[AgentTaskQueue] Laya shadow unavailable: %s", type(exc).__name__)
                        return
        try:
            self._decision_observer.submit({"objective": objective}, task_type)
        except Exception as exc:
            logger.debug("[AgentTaskQueue] Laya shadow submission failed: %s", type(exc).__name__)

    def _ensure_postgres(self) -> None:
        if self.engine.dialect.name != "postgresql":
            raise TaskQueueUnavailable(
                "The shared agent queue requires PostgreSQL and migration "
                "202610230004_priority_routine_scheduler.sql."
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)

    @staticmethod
    def _optional_identity(value: Any, field_name: str) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or len(normalized) > 200:
            raise ValueError(f"{field_name} must contain between 1 and 200 characters")
        return normalized

    def heartbeat(
        self,
        agent_id: str,
        runtime_version: str = "unknown",
        environment: str = "unknown",
        model_provider: str = "unknown",
        available_tools: list[str] | None = None,
        status: str = "available",
        concurrency_limit: int = 1,
        estimated_cost: float = 0,
        coordination_cost: float = 0,
        estimated_latency_seconds: float = 0,
    ) -> dict[str, Any]:
        self._ensure_postgres()
        if status not in {"available", "busy", "offline", "degraded"}:
            raise ValueError("Unsupported agent status")
        if not agent_id.strip():
            raise ValueError("agent_id must not be empty")
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                insert into public.jarvis_agents (
                    agent_id, runtime_version, environment, model_provider, available_tools, status,
                    concurrency_limit, estimated_cost, coordination_cost,
                    estimated_latency_seconds, last_seen_at, updated_at
                ) values (
                    :agent_id, :runtime_version, :environment, :model_provider, cast(:available_tools as jsonb),
                    :status, :concurrency_limit, :estimated_cost, :coordination_cost,
                    :estimated_latency_seconds, now(), now()
                )
                on conflict (agent_id) do update set
                    runtime_version = excluded.runtime_version,
                    environment = excluded.environment,
                    model_provider = excluded.model_provider,
                    available_tools = excluded.available_tools,
                    status = case
                        when public.jarvis_agents.status = 'busy' and excluded.status = 'available'
                        then 'busy' else excluded.status end,
                    concurrency_limit = excluded.concurrency_limit,
                    estimated_cost = excluded.estimated_cost,
                    coordination_cost = excluded.coordination_cost,
                    estimated_latency_seconds = excluded.estimated_latency_seconds,
                    last_seen_at = now(), updated_at = now()
                returning agent_id, status, active_tasks, concurrency_limit, last_seen_at
            """), {
                "agent_id": agent_id,
                "runtime_version": runtime_version,
                "environment": environment,
                "model_provider": (model_provider or "unknown").strip().lower(),
                "available_tools": self._json(available_tools or []),
                "status": status,
                "concurrency_limit": concurrency_limit,
                "estimated_cost": estimated_cost,
                "coordination_cost": coordination_cost,
                "estimated_latency_seconds": estimated_latency_seconds,
            }).mappings().one()
        return dict(row)

    def enqueue(
        self,
        task_id: str,
        objective: str,
        *,
        priority: int = 50,
        task_type: str = "general",
        required_tools: list[str] | None = None,
        constraints: list[Any] | None = None,
        acceptance_criteria: list[Any] | None = None,
        risk_level: str = "low",
        leader_id: str = "jarvis",
        parent_task_id: str | None = None,
        routine_id: str | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        expected_value: float = 1,
        max_cost: float | None = None,
        created_by: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_postgres()
        normalized_creator = self._optional_identity(created_by, "created_by")
        normalized_owner = self._optional_identity(owner_id, "owner_id")
        if not task_id.strip() or not objective.strip():
            raise ValueError("task_id and objective must not be empty")
        if not 0 <= priority <= 1000:
            raise ValueError("priority must be between 0 and 1000")
        if not 1 <= max_attempts <= 20:
            raise ValueError("max_attempts must be between 1 and 20")
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                insert into public.jarvis_agent_tasks (
                    task_id, objective, priority, task_type, required_tools, constraints,
                    acceptance_criteria, risk_level, leader_id, parent_task_id,
                    routine_id, idempotency_key, max_attempts, expected_value, max_cost,
                    created_by, owner_id, status
                ) values (
                    :task_id, :objective, :priority, :task_type, :required_tools,
                    cast(:constraints as jsonb), cast(:acceptance_criteria as jsonb),
                    :risk_level, :leader_id, :parent_task_id, :routine_id,
                    :idempotency_key, :max_attempts, :expected_value, :max_cost,
                    :created_by, :owner_id, 'ready'
                )
                on conflict (idempotency_key) where idempotency_key is not null
                do update set idempotency_key = excluded.idempotency_key
                where public.jarvis_agent_tasks.owner_id is not distinct from excluded.owner_id
                returning task_id, objective, priority, task_type, required_tools,
                          status, created_at, idempotency_key, attempts, max_attempts,
                          created_by, owner_id
            """), {
                "task_id": task_id, "objective": objective, "priority": priority,
                "task_type": task_type, "required_tools": required_tools or [],
                "constraints": self._json(constraints or []),
                "acceptance_criteria": self._json(acceptance_criteria or []),
                "risk_level": risk_level, "leader_id": leader_id,
                "parent_task_id": parent_task_id, "routine_id": routine_id,
                "idempotency_key": idempotency_key, "max_attempts": max_attempts,
                "expected_value": expected_value, "max_cost": max_cost,
                "created_by": normalized_creator, "owner_id": normalized_owner,
            }).mappings().first()
            if row is None:
                raise PermissionError("idempotency_key already belongs to another owner")
        self._submit_laya_shadow(objective, task_type)
        return dict(row)

    def claim_next(self, agent_id: str, lease_seconds: int = 90) -> dict[str, Any] | None:
        self._ensure_postgres()
        with self.engine.begin() as conn:
            conn.execute(text("select public.recover_expired_jarvis_agent_tasks()"))
            row = conn.execute(text("""
                select * from public.claim_next_jarvis_agent_task(:agent_id, :lease_seconds)
            """), {"agent_id": agent_id, "lease_seconds": lease_seconds}).mappings().first()
        return dict(row) if row else None

    def finish(
        self,
        task_id: str,
        agent_id: str,
        attempt_id: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> bool:
        self._ensure_postgres()
        with self.engine.begin() as conn:
            value = conn.execute(text("""
                select public.finish_jarvis_agent_task(
                    :task_id, :agent_id, cast(:attempt_id as uuid), :status, cast(:result as jsonb)
                )
            """), {
                "task_id": task_id, "agent_id": agent_id, "attempt_id": attempt_id,
                "status": status, "result": self._json(result or {}),
            }).scalar_one()
        return bool(value)

    def release(
        self,
        task_id: str,
        agent_id: str,
        attempt_id: str,
        reason: str = "worker error",
    ) -> bool:
        """Return a failed attempt to the queue without waiting for its lease."""
        self._ensure_postgres()
        if not task_id.strip() or not agent_id.strip() or not attempt_id.strip():
            raise ValueError("task_id, agent_id and attempt_id must not be empty")
        normalized_reason = (reason or "").strip()[:500] or "worker error"
        with self.engine.begin() as conn:
            value = conn.execute(text("""
                select public.release_jarvis_agent_task(
                    :task_id, :agent_id, cast(:attempt_id as uuid), :reason
                )
            """), {
                "task_id": task_id, "agent_id": agent_id,
                "attempt_id": attempt_id, "reason": normalized_reason,
            }).scalar_one()
        return bool(value)

    def create_routine(
        self,
        routine_key: str,
        name: str,
        *,
        priority: int = 50,
        schedule: dict[str, Any] | None = None,
        task_template: dict[str, Any] | None = None,
        enabled: bool = True,
        created_by: str | None = None,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_postgres()
        normalized_creator = self._optional_identity(created_by, "created_by")
        normalized_owner = self._optional_identity(owner_id, "owner_id")
        if not routine_key.strip() or not name.strip():
            raise ValueError("routine_key and name must not be empty")
        if not 0 <= priority <= 1000:
            raise ValueError("priority must be between 0 and 1000")
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                insert into public.jarvis_routine_definitions
                    (routine_key, name, priority, schedule, task_template, enabled,
                     created_by, owner_id)
                values (:routine_key, :name, :priority, cast(:schedule as jsonb),
                        cast(:task_template as jsonb), :enabled, :created_by, :owner_id)
                on conflict (routine_key) do update set
                    name = excluded.name, priority = excluded.priority,
                    schedule = excluded.schedule, task_template = excluded.task_template,
                    enabled = excluded.enabled, updated_at = now()
                where public.jarvis_routine_definitions.owner_id
                      is not distinct from excluded.owner_id
                returning routine_id, routine_key, name, priority, schedule,
                          task_template, enabled, last_triggered_at, created_by, owner_id
            """), {
                "routine_key": routine_key, "name": name, "priority": priority,
                "schedule": self._json(schedule or {}),
                "task_template": self._json(task_template or {}),
                "enabled": enabled,
                "created_by": normalized_creator,
                "owner_id": normalized_owner,
            }).mappings().first()
            if row is None:
                raise PermissionError("routine_key already belongs to another owner")
        return dict(row)

    def trigger_routine(
        self,
        routine_key: str,
        run_key: str,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        """Materialize one routine run as an idempotent task."""
        self._ensure_postgres()
        normalized_owner = self._optional_identity(owner_id, "owner_id")
        if not routine_key.strip() or not run_key.strip():
            raise ValueError("routine_key and run_key must not be empty")
        with self.engine.begin() as conn:
            routine = conn.execute(text("""
                select routine_id, routine_key, name, priority, task_template, enabled,
                       created_by, owner_id
                  from public.jarvis_routine_definitions
                 where routine_key = :routine_key
                 for update
            """), {"routine_key": routine_key}).mappings().first()
            if not routine:
                raise ValueError("Routine not found")
            if not routine["enabled"]:
                raise ValueError("Routine is disabled")
            routine_owner = self._optional_identity(routine["owner_id"], "owner_id")
            if routine_owner is not None and routine_owner != normalized_owner:
                raise PermissionError("Routine belongs to another owner")
            task_owner = routine_owner or normalized_owner
            task_creator = (
                self._optional_identity(routine["created_by"], "created_by")
                or normalized_owner
            )
            template = routine["task_template"] or {}
            if not isinstance(template, dict) or not template.get("objective"):
                raise ValueError("Routine task_template must contain an objective")
            row = conn.execute(text("""
                insert into public.jarvis_agent_tasks (
                    task_id, objective, priority, task_type, required_tools,
                    constraints, acceptance_criteria, risk_level, leader_id,
                    routine_id, idempotency_key, max_attempts, expected_value,
                    max_cost, created_by, owner_id, status
                ) values (
                    :task_id, :objective, :priority, :task_type, :required_tools,
                    cast(:constraints as jsonb), cast(:acceptance_criteria as jsonb),
                    :risk_level, :leader_id, :routine_id, :idempotency_key,
                    :max_attempts, :expected_value, :max_cost, :created_by, :owner_id, 'ready'
                )
                on conflict (idempotency_key) where idempotency_key is not null
                do update set idempotency_key = excluded.idempotency_key
                where public.jarvis_agent_tasks.owner_id is not distinct from excluded.owner_id
                returning task_id, objective, priority, status, created_at, idempotency_key,
                          created_by, owner_id
            """), {
                "task_id": str(uuid4()),
                "objective": template["objective"],
                "priority": int(template.get("priority", routine["priority"])),
                "task_type": template.get("task_type", "general"),
                "required_tools": template.get("required_tools", []),
                "constraints": self._json(template.get("constraints", [])),
                "acceptance_criteria": self._json(template.get("acceptance_criteria", [])),
                "risk_level": template.get("risk_level", "low"),
                "leader_id": template.get("leader_id", "jarvis"),
                "routine_id": str(routine["routine_id"]),
                "idempotency_key": f"routine:{routine_key}:{run_key}:{task_owner or 'system'}",
                "max_attempts": int(template.get("max_attempts", 3)),
                "expected_value": float(template.get("expected_value", 1)),
                "max_cost": template.get("max_cost"),
                "created_by": task_creator,
                "owner_id": task_owner,
            }).mappings().first()
            if row is None:
                raise PermissionError("routine run idempotency key belongs to another owner")
            conn.execute(text("""
                update public.jarvis_routine_definitions
                   set last_triggered_at = now(), updated_at = now()
                 where routine_id = :routine_id
            """), {"routine_id": str(routine["routine_id"])})
        return dict(row)


    def get_task_owner(self, task_id: str) -> str | None:
        """Return the persisted owner for a task, or None for legacy/internal tasks."""
        self._ensure_postgres()
        if not task_id.strip():
            raise ValueError("task_id must not be empty")
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    select owner_id
                      from public.jarvis_agent_tasks
                     where task_id = :task_id
                """),
                {"task_id": task_id},
            ).mappings().first()
        return self._optional_identity(row["owner_id"], "owner_id") if row else None
