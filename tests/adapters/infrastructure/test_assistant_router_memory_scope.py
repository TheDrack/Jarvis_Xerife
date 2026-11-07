"""Authenticated API requests must carry user identity into assistant memory."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.api_models import User
from app.adapters.infrastructure.routers.assistant import create_assistant_router


def _app_for_user(user_id: str):
    service = SimpleNamespace(
        async_process_command=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                message="ok",
                data={},
                error=None,
            )
        )
    )

    def authenticated_user():
        return User(username="commander", user_id=user_id)

    app = FastAPI()
    app.include_router(
        create_assistant_router(
            assistant_service=service,
            db_adapter=SimpleNamespace(),
            get_current_user=authenticated_user,
        )
    )
    return TestClient(app), service


def test_execute_endpoint_passes_authenticated_user_id_to_assistant():
    client, service = _app_for_user("user-alice")

    response = client.post("/v1/execute", json={"command": "remember my project"})

    assert response.status_code == 200
    service.async_process_command.assert_awaited_once()
    kwargs = service.async_process_command.await_args.kwargs
    assert kwargs["request_metadata"]["user_id"] == "user-alice"


def test_message_endpoint_passes_authenticated_user_id_to_assistant():
    client, service = _app_for_user("user-bob")

    response = client.post("/v1/message", json={"text": "recall my project"})

    assert response.status_code == 200
    service.async_process_command.assert_awaited_once()
    kwargs = service.async_process_command.await_args.kwargs
    assert kwargs["request_metadata"]["user_id"] == "user-bob"


def test_history_endpoint_requires_authenticated_user_scope():
    client, service = _app_for_user("user-charlie")
    seen_user_ids = []
    def get_user_history(*, limit, user_id):
        seen_user_ids.append(user_id)
        return [
        {
            "command": "charlie private command",
            "timestamp": "2026-11-06T12:00:00",
            "success": True,
            "message": "private response",
        }
    ]
    service.get_command_history = get_user_history

    response = client.get("/v1/history")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["commands"][0]["command"] == "charlie private command"
    assert seen_user_ids == ["user-charlie"]
