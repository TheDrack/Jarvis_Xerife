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
        calls.append((request.url.path, body, request.headers["Authorization"], request.headers["X-Jarvis-Worker-Token"]))
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
        worker_token="worker-test-token",
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
    assert all(call[3] == "worker-test-token" for call in calls)
    assert worker_handler.messages[0].payload["objective"] == "Summarize the supplied context"


def test_priority_worker_returns_none_when_queue_empty():
    def handler(request):
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={"status": "available"})
        return httpx.Response(200, json={"task": None})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="token",
        worker_token="worker-test-token", agent_id="mini-1", handler=FakeHandler(), client=client,
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
        worker_token="worker-test-token",
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
        worker_token="worker-test-token",
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
        worker_token="worker-test-token", agent_id="mini-1", username="agent@example.test", password="not-logged",
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



def test_from_env_resolves_slot_specific_worker_credential(monkeypatch):
    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_TOKEN", "user-jwt")
    monkeypatch.setenv("JARVIS_MINI_AGENT_WORKERS", "2")
    monkeypatch.setenv("JARVIS_TASK_QUEUE_WORKER_TOKEN_MINI_FREELLMAPI_2", "slot-two-token")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "provider-key")
    monkeypatch.setattr(
        "app.multiagent.priority_queue_mini_agent.FreeLLMAPIClient.from_env",
        lambda agent_id=None: object(),
    )
    monkeypatch.setattr(
        "app.multiagent.priority_queue_mini_agent.create_registered_model_handler",
        lambda *args, **kwargs: lambda task: {},
    )
    monkeypatch.setattr(
        "app.multiagent.priority_queue_mini_agent.configured_provider_id",
        lambda agent_id=None: "groq",
    )

    worker = PriorityQueueMiniAgent.from_env(agent_id="mini-freellmapi-2")

    assert worker.worker_token == "slot-two-token"


def test_from_env_does_not_reuse_global_token_for_multiple_slots(monkeypatch):
    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_TOKEN", "user-jwt")
    monkeypatch.setenv("JARVIS_MINI_AGENT_WORKERS", "2")
    monkeypatch.setenv("JARVIS_TASK_QUEUE_WORKER_TOKEN", "shared-token")
    monkeypatch.delenv("JARVIS_TASK_QUEUE_WORKER_TOKEN_MINI_FREELLMAPI_1", raising=False)
    monkeypatch.setenv("FREELLMAPI_API_KEY", "provider-key")

    with pytest.raises(RuntimeError, match="JARVIS_TASK_QUEUE_WORKER_TOKEN"):
        PriorityQueueMiniAgent.from_env(agent_id="mini-freellmapi-1")


def test_priority_worker_advertises_configured_runtime_environment(monkeypatch):
    calls = []
    monkeypatch.setenv("JARVIS_AGENT_ENVIRONMENT", "termux-android")

    def transport(request):
        import json
        calls.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={"status": "available"})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": None})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="token",
        worker_token="worker-test-token", agent_id="jarvis-termux-mini-1",
        handler=FakeHandler(), client=client,
    )
    try:
        assert worker.run_once() is None
    finally:
        client.close()

    heartbeat = next(body for path, body in calls if path.endswith("/heartbeat"))
    assert heartbeat["environment"] == "termux-android"


def test_from_env_remote_inference_needs_no_jwt_or_provider_key(monkeypatch):
    from app.multiagent.remote_inference_client import RemoteInferenceHandler

    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_AGENT_REMOTE_INFERENCE", "true")
    monkeypatch.setenv("JARVIS_AGENT_ID", "jarvis-termux-mini-1")
    monkeypatch.delenv("JARVIS_TASK_QUEUE_API_TOKEN", raising=False)
    monkeypatch.delenv("JARVIS_TASK_QUEUE_USERNAME", raising=False)
    monkeypatch.delenv("JARVIS_TASK_QUEUE_PASSWORD", raising=False)
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("VENICE_API_KEY", raising=False)

    worker = PriorityQueueMiniAgent.from_env(
        worker_token="preprovisioned-worker-token",
    )

    assert worker.remote_inference is True
    assert worker.api_token == ""
    assert isinstance(worker.handler, RemoteInferenceHandler)


def test_remote_mode_worker_requests_do_not_send_user_jwt():
    requests = []

    def transport(request):
        requests.append(request)
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={"status": "available"})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": None})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", worker_token="worker-only-token",
        agent_id="jarvis-termux-mini-1", handler=FakeHandler(),
        remote_inference=True, client=client,
    )
    try:
        assert worker.run_once() is None
    finally:
        client.close()

    assert len(requests) == 2
    assert all(request.headers["X-Jarvis-Worker-Token"] == "worker-only-token" for request in requests)
    assert all("Authorization" not in request.headers for request in requests)


def test_priority_worker_renews_lease_while_handler_is_running(monkeypatch):
    import threading

    renewed = threading.Event()
    calls = []

    def transport(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": {
                "task_id": "task-lease", "attempt_id": "00000000-0000-0000-0000-000000000031",
                "objective": "Long running task",
            }})
        if request.url.path.endswith("/renew"):
            renewed.set()
            return httpx.Response(200, json={"renewed": True})
        if request.url.path.endswith("/finish"):
            return httpx.Response(200, json={"accepted": True})
        raise AssertionError(request.url.path)

    class BlockingHandler:
        def __call__(self, message):
            assert renewed.wait(2), "worker did not renew the active lease"
            return {"success": True, "output": "done"}

    monkeypatch.setattr(PriorityQueueMiniAgent, "_lease_renewal_interval", lambda self: 0.01)
    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="user-token",
        worker_token="worker-token", agent_id="mini-1", handler=BlockingHandler(),
        client=client,
    )
    try:
        result = worker.run_once()
    finally:
        client.close()

    assert result["status"] == "completed"
    assert "/v1/agent-tasks/task-lease/renew" in calls
    assert calls.index("/v1/agent-tasks/task-lease/renew") < calls.index("/v1/agent-tasks/task-lease/finish")


def test_priority_worker_does_not_finish_when_lease_renewal_is_rejected(monkeypatch):
    import threading

    renew_rejected = threading.Event()
    calls = []

    def transport(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": {
                "task_id": "task-stale", "attempt_id": "00000000-0000-0000-0000-000000000032",
                "objective": "Stale task",
            }})
        if request.url.path.endswith("/renew"):
            renew_rejected.set()
            return httpx.Response(409, json={"detail": "Task ownership or lease is stale"})
        if request.url.path.endswith("/release"):
            return httpx.Response(200, json={"released": False})
        if request.url.path.endswith("/finish"):
            raise AssertionError("a stale attempt must never be completed")
        raise AssertionError(request.url.path)

    class BlockingHandler:
        def __call__(self, message):
            assert renew_rejected.wait(2), "worker did not attempt lease renewal"
            return {"success": True, "output": "must be discarded"}

    monkeypatch.setattr(PriorityQueueMiniAgent, "_lease_renewal_interval", lambda self: 0.01)
    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", api_token="user-token",
        worker_token="worker-token", agent_id="mini-1", handler=BlockingHandler(),
        client=client,
    )
    try:
        with pytest.raises(RuntimeError, match="lease.*lost"):
            worker.run_once()
    finally:
        client.close()

    assert not any(path.endswith("/finish") for path in calls)


def test_from_env_supports_an_openai_compatible_vendor_api_with_its_own_key(monkeypatch):
    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_AGENT_REMOTE_INFERENCE", "false")
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER", "gemini")
    monkeypatch.setenv("JARVIS_AGENT_ID", "gemini-worker")
    monkeypatch.setenv("JARVIS_TASK_QUEUE_WORKER_TOKEN_GEMINI_WORKER", "worker-only-token")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "vendor-api-key")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    monkeypatch.setenv("FREELLMAPI_MODEL", "gemini-2.5-flash")
    monkeypatch.delenv("JARVIS_TASK_QUEUE_API_TOKEN", raising=False)
    captured = {}

    def make_handler(client, *, provider_id):
        captured["client"] = client
        captured["provider_id"] = provider_id
        return FakeHandler()

    monkeypatch.setattr(
        "app.multiagent.priority_queue_mini_agent.create_registered_model_handler",
        make_handler,
    )

    worker = PriorityQueueMiniAgent.from_env()

    assert worker.api_token == ""
    assert worker.worker_token == "worker-only-token"
    assert captured["provider_id"] == "gemini"
    assert captured["client"].base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert captured["client"].model == "gemini-2.5-flash"


def test_from_env_selects_a_different_provider_for_each_agent(monkeypatch):
    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_AGENT_REMOTE_INFERENCE", "true")
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER", "groq")
    monkeypatch.setenv("JARVIS_AGENT_REMOTE_INFERENCE_GEMINI_WORKER", "false")
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER_GEMINI_WORKER", "gemini")
    monkeypatch.setenv("JARVIS_TASK_QUEUE_WORKER_TOKEN_GEMINI_WORKER", "worker-token")
    monkeypatch.setenv("FREELLMAPI_API_KEY_GEMINI_WORKER", "gemini-key")
    monkeypatch.setenv("FREELLMAPI_BASE_URL_GEMINI_WORKER", "https://generativelanguage.googleapis.com/v1beta")
    monkeypatch.setenv("FREELLMAPI_MODEL_GEMINI_WORKER", "gemini-model")
    captured = {}

    def make_handler(client, *, provider_id):
        captured["client"] = client
        captured["provider_id"] = provider_id
        return FakeHandler()

    monkeypatch.setattr(
        "app.multiagent.priority_queue_mini_agent.create_registered_model_handler",
        make_handler,
    )

    worker = PriorityQueueMiniAgent.from_env(
        agent_id="gemini-worker", worker_token="worker-token"
    )

    assert worker.remote_inference is False
    assert captured["provider_id"] == "gemini"
    assert captured["client"].api_key == "gemini-key"
    assert captured["client"].base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert captured["client"].model == "gemini-model"


def test_explicit_venice_agent_does_not_fall_back_to_global_groq(monkeypatch):
    from app.multiagent.freellmapi_client import FreeLLMAPIClient

    monkeypatch.setenv("GROQ_API_KEY", "global-groq-key")
    monkeypatch.setenv("VENICE_API_KEY_VENICE_WORKER", "agent-venice-key")
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER_VENICE_WORKER", "venice")

    client = FreeLLMAPIClient.from_env(agent_id="venice-worker")

    assert client.api_key == "agent-venice-key"
    assert client.base_url == "https://api.venice.ai/api/v1"
    assert client.model == "venice-uncensored-1-2"


def test_generic_vendor_provider_rejects_auto_model(monkeypatch):
    from app.multiagent.freellmapi_client import FreeLLMAPIClient, FreeLLMAPIError

    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER", "gemini")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "vendor-key")
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    monkeypatch.setenv("FREELLMAPI_MODEL", "auto")

    with pytest.raises(FreeLLMAPIError, match="requires FREELLMAPI_API_KEY"):
        FreeLLMAPIClient.from_env()


def test_from_env_binds_android_app_runtime_per_agent_without_api_credentials(monkeypatch):
    from app.adapters.infrastructure.android_app_model_runtime import (
        AndroidAppLLMRuntimeAdapter,
    )

    agent_id = "jarvis-termux-mini-1"
    monkeypatch.setenv("JARVIS_TASK_QUEUE_API_URL", "https://jarvis.example")
    monkeypatch.setenv("JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_TERMUX_MINI_1", "worker-token")
    monkeypatch.setenv("JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_TERMUX_MINI_1", "false")
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER_JARVIS_TERMUX_MINI_1", "android_app:claude")
    for key in ("FREELLMAPI_API_KEY", "GROQ_API_KEY", "VENICE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        "app.multiagent.priority_queue_mini_agent.FreeLLMAPIClient.from_env",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("app runtime must not require API credentials")),
    )

    worker = PriorityQueueMiniAgent.from_env(agent_id=agent_id)

    assert worker.remote_inference is False
    assert isinstance(worker.handler.runtime, AndroidAppLLMRuntimeAdapter)
    assert worker.handler.runtime.provider_id == "android_app:claude"


def test_android_app_worker_heartbeat_reports_its_configured_provider(monkeypatch):
    import json

    calls = []
    agent_id = "jarvis-termux-mini-1"
    monkeypatch.setenv("JARVIS_AGENT_MODEL_PROVIDER_JARVIS_TERMUX_MINI_1", "android_app:claude")

    def transport(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        if request.url.path.endswith("/heartbeat"):
            return httpx.Response(200, json={"status": "available"})
        if request.url.path.endswith("/claim-next"):
            return httpx.Response(200, json={"task": None})
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    worker = PriorityQueueMiniAgent(
        api_base_url="https://jarvis.example", worker_token="worker-token",
        agent_id=agent_id, handler=FakeHandler(), client=client,
    )
    try:
        assert worker.run_once() is None
    finally:
        client.close()

    heartbeat = next(body for path, body in calls if path.endswith("/heartbeat"))
    assert heartbeat["model_provider"] == "android_app:claude"
