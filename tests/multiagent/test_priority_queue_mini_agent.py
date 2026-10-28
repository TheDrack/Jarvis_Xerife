from __future__ import annotations

import httpx
import pytest

from app.multiagent.priority_queue_mini_agent import PriorityQueueMiniAgent


class FakeHandler:
    def __init__(self, result=None, error=None):
        self.result = result or {"success": True, "output": "summary", "engine": "freellmapi"}
        self.error = error
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)
        if self.error:
            raise self.error
        return self.result


def response_for(path, body):
    return httpx.Response(200, json=body)


def test_priority_worker_heartbeats_claims_and_finishes_one_task():
    calls = []
    def handler(request):
        body = __import__("json").loads(request.content)
        calls.append((request.url.path, body, request.headers["Authorization"]))
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={"agent_id": "mini-1", "status": "available"})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": {
                "task_id": "task-22", "attempt_id": "00000000-0000-0000-0000-000000000022",
                "objective": "Summarize the supplied context", "leader_id": "leader",
                "task_type": "research", "constraints": ["Do not invent sources"],
                "acceptance_criteria": ["Mention uncertainty"], "context": "One observation.",
            }})
        if request.url.path.endswith("/finish"):
            return httpx.Response(200, json={"accepted": True})
        raise AssertionError(request.url.path)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    worker_handler = FakeHandler()
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example",
        api_token="api-test-token",
        agent_id="mini-1",
        handler=worker_handler,
        client=http_client,
    )
    try:
        result = worker.run_once()
    finally:
        http_client.close()

    assert result["status"] == "completed"
    assert [call[0] for call in calls] == [
        "/v1/agents/heartbeat", "/v1/agent-tasks/claim-next", "/v1/agent-tasks/task-22/finish"
    ]
    assert calls[0][1]["available_tools"] == ["text_reasoning"]
    assert calls[1][1]["lease_seconds"] == 90
    assert calls[2][1]["status"] == "completed"
    assert calls[2][1]["attempt_id"].endswith("0022")
    assert all(call[2] == "Bearer api-test-token" for call in calls)
    assert worker_handler.messages[0].payload["objective"] == "Summarize the supplied context"


def test_priority_worker_returns_none_when_queue_empty():
    def handler(request):
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={"status": "available"})
        return httpx.Response(200, json={"task": None})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="token",
        agent_id="mini-1", handler=FakeHandler(), client=client,
    )
    try:
        assert worker.run_once() is None
    finally:
        client.close()


def test_priority_worker_releases_task_when_inference_raises():
    calls = []

    def transport(request):
        body = __import__("json").loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": {
                "task_id": "task-23", "attempt_id": "00000000-0000-0000-0000-000000000023",
                "objective": "Do bounded analysis",
            }})
        if request.url.path.endswith("/release"):
            return httpx.Response(200, json={"released": True})
        raise AssertionError(f"unexpected call {request.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="token",
        agent_id="mini-1", handler=FakeHandler(error=RuntimeError("model unavailable")),
        client=client,
    )
    try:
        with pytest.raises(RuntimeError, match="model unavailable"):
            worker.run_once()
    finally:
        client.close()

    paths = [path for path, _ in calls]
    assert "/v1/agent-tasks/task-23/release" in paths, "the HTTP worker must release at once"
    assert not any(path.endswith("/finish") for path in paths), "no fabricated completion"
    release = next(body for path, body in calls if path.endswith("/release"))
    assert release["agent_id"] == "mini-1"
    assert release["attempt_id"] == "00000000-0000-0000-0000-000000000023"
    assert "model unavailable" in release["reason"]


def test_priority_worker_keeps_original_error_when_release_endpoint_fails():
    paths = []

    def transport(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": {
                "task_id": "task-24", "attempt_id": "00000000-0000-0000-0000-000000000024",
                "objective": "Do bounded analysis",
            }})
        if request.url.path.endswith("/release"):
            return httpx.Response(503, json={"detail": "queue unavailable"})
        raise AssertionError(f"unexpected call {request.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="token",
        agent_id="mini-1", handler=FakeHandler(error=RuntimeError("model unavailable")),
        client=client,
    )
    try:
        with pytest.raises(RuntimeError, match="model unavailable"):
            worker.run_once()
    finally:
        client.close()
    assert any(path.endswith("/release") for path in paths)



def test_priority_worker_can_login_and_refresh_expired_jwt():
    calls = []
    def transport(request):
        calls.append((request.url.path, request.headers.get("Authorization")))
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "fresh-jwt"})
        if request.url.path.endswith("/heartbeat"):
            if request.headers.get("Authorization") == "Bearer stale-jwt":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json={})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": None})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="stale-jwt",
        agent_id="mini-1", username="agent@example.test", password="not-logged",
        handler=FakeHandler(), client=client,
    )
    try:
        assert worker.run_once() is None
    finally:
        client.close()

    assert calls[0] == ("/v1/agents/heartbeat", "Bearer stale-jwt")
    assert calls[1] == ("/token", None)
    assert calls[2] == ("/v1/agents/heartbeat", "Bearer fresh-jwt")
    assert worker.api_token == "fresh-jwt"
