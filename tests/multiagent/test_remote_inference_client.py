from __future__ import annotations

import json

import httpx

from app.multiagent.remote_inference_client import RemoteInferenceHandler
from app.multiagent.transport import AgentMessage


def test_remote_inference_sends_worker_token_and_bounded_text_payload():
    captured = []

    def transport(request):
        captured.append(request)
        return httpx.Response(200, json={"result": {"success": True, "output": "analysis"}})

    client = httpx.Client(transport=httpx.MockTransport(transport))
    handler = RemoteInferenceHandler(
        api_base_url="https://jarvis.example",
        worker_token="worker-secret",
        agent_id="mini-1",
        client=client,
    )
    message = AgentMessage.create(
        task_id="task-1",
        sender_id="leader",
        recipient_id="mini-1",
        kind="request",
        payload={
            "objective": "Analyze objective",
            "attempt_id": "00000000-0000-0000-0000-000000000001",
            "task_type": "analysis",
            "context": "Provided context",
            "constraints": ["No tools"],
            "acceptance_criteria": ["Be accurate"],
            "model": "llama-test",
        },
    )

    try:
        result = handler(message)
    finally:
        client.close()

    request = captured[0]
    assert request.url.path == "/v1/agent-inference/complete"
    assert request.headers["X-Jarvis-Worker-Token"] == "worker-secret"
    assert "Authorization" not in request.headers
    assert json.loads(request.content)["attempt_id"] == "00000000-0000-0000-0000-000000000001"
    assert result == {"success": True, "output": "analysis"}


def test_remote_inference_rejects_non_request_messages():
    handler = RemoteInferenceHandler(
        api_base_url="https://jarvis.example",
        worker_token="worker-secret",
        agent_id="mini-1",
    )
    message = AgentMessage.create(
        task_id="task-1", sender_id="leader", recipient_id="mini-1",
        kind="ack", payload={},
    )

    result = handler(message)

    assert result == {"success": False, "error": "unsupported_message_kind"}
