"""Real two-process integration test against an isolated local Supabase stack.

The test is opt-in and only runs when the dedicated workflow supplies its
ephemeral Supabase URL and service-role key. The leader and worker each create
their own Supabase client; no in-memory database or shared Python object crosses
the process boundary.
"""
from __future__ import annotations

import multiprocessing
import os
import queue
import uuid
from typing import Any


def _handle_message(message: Any) -> dict[str, Any]:
    if message.kind != "request":
        raise ValueError(f"unexpected message kind: {message.kind}")
    assignment = message.payload.get("assignment")
    if not isinstance(assignment, dict):
        raise ValueError("leader request does not contain a task assignment")
    return {
        "success": True,
        "task_id": message.task_id,
        "worker_pid": os.getpid(),
        "assignment_task_id": assignment.get("task_id"),
    }


def _run_worker_process(
    supabase_url: str,
    service_role_key: str,
    worker_id: str,
    result_queue: multiprocessing.Queue,
) -> None:
    """Create an independent client inside the spawned worker process."""
    try:
        from supabase import create_client

        from app.multiagent import AgentWorker, SupabaseQueueConnector

        client = create_client(supabase_url, service_role_key)
        connector = SupabaseQueueConnector(
            client,
            lease_seconds=30,
            poll_interval_seconds=0.05,
        )
        worker = AgentWorker(worker_id, connector, _handle_message)
        processed = worker.process_once(timeout_seconds=15)
        result_queue.put(
            {
                "processed": processed,
                "pid": os.getpid(),
                "error": None,
            }
        )
    except BaseException as exc:
        result_queue.put(
            {
                "processed": False,
                "pid": os.getpid(),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        raise


def test_leader_and_worker_exchange_messages_across_real_processes_and_postgrest():
    supabase_url = os.getenv("JARVIS_E2E_SUPABASE_URL")
    service_role_key = os.getenv("JARVIS_E2E_SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        import pytest

        pytest.skip("requires the dedicated isolated Supabase process-E2E workflow")

    from supabase import create_client

    from app.multiagent import (
        AgentLeader,
        AgentProfile,
        SupabaseQueueConnector,
        TaskSpec,
    )

    suffix = uuid.uuid4().hex
    leader_id = f"e2e-leader-{suffix}"
    worker_id = f"e2e-worker-{suffix}"
    task_id = f"e2e-task-{suffix}"

    # This client lives in the parent process; the worker builds another client.
    leader_client = create_client(supabase_url, service_role_key)
    leader_connector = SupabaseQueueConnector(
        leader_client,
        lease_seconds=30,
        poll_interval_seconds=0.05,
    )
    leader = AgentLeader(leader_id, leader_connector)
    task = TaskSpec(
        task_id=task_id,
        objective="Verify a bounded operation in a distinct worker process",
        required_tools=("text_reasoning",),
        task_type="process_e2e",
        acceptance_criteria=("Return the task ID and worker PID",),
    )
    profile = AgentProfile(
        worker_id,
        available_tools=("text_reasoning",),
        estimated_cost=0.1,
        success_rates={"process_e2e": 1.0},
    )

    dispatch = leader.dispatch(task, [profile])
    assert dispatch.assignment.assigned_agent_id == worker_id

    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    worker_process = context.Process(
        target=_run_worker_process,
        args=(
            supabase_url,
            service_role_key,
            worker_id,
            result_queue,
        ),
        name=f"jarvis-e2e-{worker_id}",
    )

    worker_process.start()
    worker_process.join(timeout=25)
    if worker_process.is_alive():
        worker_process.terminate()
        worker_process.join(timeout=5)
        raise AssertionError("worker process did not finish within 25 seconds")

    assert worker_process.exitcode == 0
    try:
        worker_result = result_queue.get(timeout=3)
    except queue.Empty as exc:
        raise AssertionError("worker exited without reporting its result") from exc

    assert worker_result["error"] is None
    assert worker_result["processed"] is True
    assert worker_result["pid"] == worker_process.pid
    assert worker_result["pid"] != os.getpid()

    response = leader_connector.receive(leader_id, timeout_seconds=15)
    assert response is not None
    assert response.kind == "result"
    assert response.task_id == task_id
    assert response.sender_id == worker_id
    assert response.recipient_id == leader_id
    assert response.correlation_id == dispatch.message_id
    assert response.payload["result"] == {
        "success": True,
        "task_id": task_id,
        "worker_pid": worker_process.pid,
        "assignment_task_id": task_id,
    }
    assert leader_connector.acknowledge(
        response.message_id,
        leader_id,
        claim_token=response.claim_token,
    ) is True
