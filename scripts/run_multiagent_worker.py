"""Run one supervised Jarvis multi-agent worker against the shared Supabase queue.

Required environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
JARVIS_AGENT_ID, FREELLMAPI_API_KEY. This worker performs text-only inference;
it does not grant tools or execute filesystem/desktop side effects.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from app.multiagent import AgentProfile, AgentWorker, FreeLLMAPIClient, FreeLLMAgentHandler, SupabaseAgentStore, SupabaseQueueConnector

LOG = logging.getLogger("jarvis.multiagent.worker")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not configured")
    return value


def _build_profile(agent_id: str) -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        available_tools=("text.analysis", "task.respond"),
        status="available",
        concurrency_limit=1,
        estimated_cost=float(os.getenv("JARVIS_AGENT_ESTIMATED_COST", "0.1")),
        coordination_cost=float(os.getenv("JARVIS_AGENT_COORDINATION_COST", "0.01")),
        estimated_latency_seconds=float(os.getenv("JARVIS_AGENT_LATENCY_SECONDS", "15")),
        environment=os.getenv("JARVIS_AGENT_ENVIRONMENT", "worker"),
        model_provider=os.getenv("JARVIS_AGENT_MODEL_PROVIDER", "freellmapi").strip().lower(),
    )


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("JARVIS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    agent_id = _required_env("JARVIS_AGENT_ID")
    supabase = create_client(_required_env("SUPABASE_URL"), _required_env("SUPABASE_SERVICE_ROLE_KEY"))
    profile = _build_profile(agent_id)
    store = SupabaseAgentStore(supabase)
    queue = SupabaseQueueConnector(
        supabase,
        lease_seconds=int(os.getenv("JARVIS_QUEUE_LEASE_SECONDS", "120")),
        poll_interval_seconds=float(os.getenv("JARVIS_QUEUE_POLL_SECONDS", "0.5")),
    )
    inference = FreeLLMAPIClient.from_env()
    handler = FreeLLMAgentHandler(
        inference,
        max_tokens=int(os.getenv("JARVIS_AGENT_MAX_TOKENS", "1200")),
        temperature=float(os.getenv("JARVIS_AGENT_TEMPERATURE", "0.2")),
    )
    worker = AgentWorker(agent_id, queue, handler)
    stop = threading.Event()

    def request_stop(signum: int, _frame: Any) -> None:
        LOG.info("Shutdown signal received (%s)", signum)
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    heartbeat_seconds = max(5.0, float(os.getenv("JARVIS_AGENT_HEARTBEAT_SECONDS", "20")))
    next_heartbeat = 0.0
    processed = 0
    store.register_agent(profile, runtime_version="multiagent-worker/1.0", environment=profile.environment)
    LOG.info("Worker started: agent_id=%s provider=%s; text-only handler enabled", agent_id, profile.model_provider)
    try:
        while not stop.is_set():
            now = time.monotonic()
            if now >= next_heartbeat:
                heartbeat_profile = AgentProfile(
                    agent_id=profile.agent_id,
                    available_tools=profile.available_tools,
                    status="available",
                    active_tasks=0,
                    concurrency_limit=profile.concurrency_limit,
                    estimated_cost=profile.estimated_cost,
                    coordination_cost=profile.coordination_cost,
                    success_rates=profile.success_rates,
                    estimated_latency_seconds=profile.estimated_latency_seconds,
                    environment=profile.environment,
                    model_provider=profile.model_provider,
                )
                store.register_agent(heartbeat_profile, runtime_version="multiagent-worker/1.0", environment=profile.environment)
                next_heartbeat = now + heartbeat_seconds
            try:
                if worker.process_once(timeout_seconds=min(1.0, heartbeat_seconds)):
                    processed += 1
                    LOG.info("Processed message count=%s", processed)
            except Exception:
                LOG.exception("Message processing failed; unacknowledged messages can be redelivered")
                stop.wait(min(2.0, heartbeat_seconds))
    finally:
        try:
            store.register_agent(AgentProfile(
                agent_id=profile.agent_id,
                available_tools=profile.available_tools,
                status="offline",
                concurrency_limit=profile.concurrency_limit,
                estimated_cost=profile.estimated_cost,
                coordination_cost=profile.coordination_cost,
                estimated_latency_seconds=profile.estimated_latency_seconds,
                environment=profile.environment,
                model_provider=profile.model_provider,
            ), runtime_version="multiagent-worker/1.0", environment=profile.environment)
        except Exception:
            LOG.exception("Could not mark agent offline during shutdown")
        LOG.info("Worker stopped; processed=%s", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
