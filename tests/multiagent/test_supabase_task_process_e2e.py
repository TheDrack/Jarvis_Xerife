"""Real multi-process E2E for the Supabase-native task worker.

The dedicated GitHub workflow supplies an ephemeral local Supabase instance.
The parent process enqueues a task; a spawned child creates its own client,
claims the task, renews its lease, executes bounded work, and commits completion.
"""
from __future__ import annotations

import multiprocessing
import os
import queue
import time
import uuid
from typing import Any


def _run_task_worker_process(
    supabase_url: str,
    service_role_key: str,
    agent_id: str,
    result_queue: multiprocessing.Queue,
) -> None:
    """Create a fresh Supabase client and execute one task in a child process."""
    try:
        from supabase import create_client

        from app.multiagent.supabase_task_worker import SupabaseTaskQueueMiniAgent

        def handle_task(message: Any) -> dict[str, Any]:
            if message.kind != "request":
                raise ValueError(f"unexpected task message kind: {message.kind}")
            if message.payload.get("objective") != "prove task execution crosses process boundaries":
                raise ValueError("unexpected task objective")
            # Keep the claim alive long enough to exercise the renewal RPC.
            time.sleep(1.0)
            return {
                "success": True,
                "output": "task completed by independent worker",
                "worker_pid": os.getpid(),
            }

        client = create_client(supabase_url, service_role_key)
        worker = SupabaseTaskQueueMiniAgent(
            client=client,
            agent_id=agent_id,
            handler=handle_task,
            lease_seconds=10,
            model_provider="openai",
        )
        worker._lease_renewal_interval = lambda: 0.1
        result = worker.run_once()
        result_queue.put(
            {"result": result, "pid": os.getpid(), "error": None}
        )
    except BaseException as exc:
        result_queue.put(
            {
                "result": None,
                "pid": os.getpid(),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        raise


def test_task_is_claimed_executed_renewed_and_completed_across_processes():
    supabase_url = os.getenv("JARVIS_TASK_E2E_SUPABASE_URL")
    service_role_key = os.getenv("JARVIS_TASK_E2E_SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        import pytest

        pytest.skip("requires the isolated Supabase task-worker process-E2E workflow")

    from supabase import create_client

    suffix = uuid.uuid4().hex
    agent_id = f"task-e2e-worker-{suffix}"
    task_id = f"task-e2e-{suffix}"

    # The parent owns only task creation and post-run assertions.
    parent_client = create_client(supabase_url, service_role_key)
    parent_client.table("jarvis_agent_tasks").insert(
        {
            "task_id": task_id,
            "objective": "prove task execution crosses process boundaries",
            "task_type": "process_e2e",
            "required_tools": ["text_reasoning"],
            "constraints": ["no external side effects"],
            "acceptance_criteria": ["persist a completed result"],
            "status": "ready",
            "leader_id": f"task-e2e-leader-{suffix}",
            "priority": 900,
        }
    ).execute()

    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    worker_process = context.Process(
        target=_run_task_worker_process,
        args=(supabase_url, service_role_key, agent_id, result_queue),
        name=f"jarvis-task-e2e-{suffix}",
    )
    worker_process.start()
    worker_process.join(timeout=35)

    if worker_process.is_alive():
        worker_process.terminate()
        worker_process.join(timeout=5)
        raise AssertionError("task worker process did not finish within 35 seconds")

    try:
        worker_result = result_queue.get(timeout=5)
    except queue.Empty as exc:
        raise AssertionError("task worker exited without reporting its result") from exc

    assert worker_process.exitcode == 0
    assert worker_result["error"] is None
    assert worker_result["pid"] == worker_process.pid
    assert worker_result["pid"] != os.getpid()
    assert worker_result["result"] == {
        "task_id": task_id,
        "status": "completed",
        "result": {
            "success": True,
            "output": "task completed by independent worker",
            "worker_pid": worker_process.pid,
        },
    }

    task_response = (
        parent_client.table("jarvis_agent_tasks")
        .select("*")
        .eq("task_id", task_id)
        .execute()
    )
    task_rows = getattr(task_response, "data", None) or []
    assert len(task_rows) == 1
    task_row = task_rows[0]
    assert task_row["status"] == "completed"
    assert task_row["attempts"] == 1
    assert task_row["assigned_agent_id"] == agent_id
    assert task_row["result"]["worker_pid"] == worker_process.pid

    event_response = (
        parent_client.table("jarvis_agent_events")
        .select("event_type,payload")
        .eq("task_id", task_id)
        .execute()
    )
    event_types = [
        row["event_type"]
        for row in (getattr(event_response, "data", None) or [])
    ]
    assert "task.claimed" in event_types
    assert "task.lease_renewed" in event_types
    assert "task.completed" in event_types

    attempt_response = (
        parent_client.table("jarvis_agent_attempts")
        .select("status,task_id,agent_id")
        .eq("task_id", task_id)
        .execute()
    )
    attempts = getattr(attempt_response, "data", None) or []
    assert len(attempts) == 1
    assert attempts[0]["status"] == "completed"
    assert attempts[0]["agent_id"] == agent_id
