from app.adapters.infrastructure.chatgpt_plan_runtime import (
    PLAN_USAGE_SCOPE,
    RESOURCE_INVOKE_SCOPE,
)
from app.multiagent.model_runtime_factory import create_registered_chatgpt_plan_runtime


class FakeOAuth:
    def load_valid_profile(self):
        return {
            "access_token": "initial-token",
            "scopes": [PLAN_USAGE_SCOPE, RESOURCE_INVOKE_SCOPE],
        }

    def get_access_token(self):
        return "rotated-token"


def test_chatgpt_plan_runtime_is_registered_without_exposing_credentials():
    profile, bindings = create_registered_chatgpt_plan_runtime(
        FakeOAuth(), model_id="gpt-6.1-sol"
    )
    runtime = bindings.resolve(profile)

    assert profile.provider_id == "chatgpt_plan"
    assert profile.model_id == "gpt-6.1-sol"
    assert profile.metadata["authentication"] == "sign_in_with_chatgpt"
    assert bindings.list_provider_ids() == ("chatgpt_plan",)
    assert runtime.client._access_token == "initial-token"
    assert runtime.token_provider() == "rotated-token"
    runtime.close()


def test_chatgpt_plan_runtime_requires_both_inference_scopes():
    class IncompleteOAuth(FakeOAuth):
        def load_valid_profile(self):
            return {"access_token": "token", "scopes": [PLAN_USAGE_SCOPE]}

    import pytest

    with pytest.raises(ValueError, match="does not grant"):
        create_registered_chatgpt_plan_runtime(
            IncompleteOAuth(), model_id="gpt-6.1-sol"
        )


def test_chatgpt_plan_handler_can_be_injected_into_existing_local_agent_pipeline():
    from app.multiagent.model_runtime_factory import (
        create_registered_chatgpt_plan_handler,
    )
    from app.multiagent.transport import AgentMessage

    handler = create_registered_chatgpt_plan_handler(
        FakeOAuth(), model_id="gpt-6.1-sol"
    )
    handler.runtime.client.generate = lambda messages, **kwargs: {
        "content": "resultado do ChatGPT",
        "model": "gpt-6.1-sol",
        "request_id": "resp_1",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }
    message = AgentMessage.create(
        task_id="task-1",
        sender_id="leader",
        recipient_id="jarvis-local",
        kind="request",
        payload={"objective": "Analise o texto."},
    )

    result = handler(message)

    assert result["success"] is True
    assert result["engine"] == "chatgpt_plan"
    assert result["provider"] == "chatgpt_plan"
    assert result["output"] == "resultado do ChatGPT"
    handler.close()
