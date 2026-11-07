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
