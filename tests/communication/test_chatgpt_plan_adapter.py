import pytest
from app.communication.chatgpt_plan import ChatGPTPlanCommunicationAdapter


class FakeOAuth:
    def __init__(self):
        self.closed = False

    def get_access_token(self):
        return "runtime-token"

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.messages = None

    def generate(self, messages, **kwargs):
        self.messages = messages
        return {
            "content": "response",
            "model": "model-x",
            "request_id": "req-1",
            "usage": {"total_tokens": 10},
        }

    def close(self):
        self.closed = True


def test_chatgpt_adapter_calls_existing_plan_runtime_and_closes_resources():
    oauth = FakeOAuth()
    clients = []

    def client_factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    adapter = ChatGPTPlanCommunicationAdapter(
        oauth_factory=lambda: oauth, client_factory=client_factory
    )
    result = adapter.execute(
        "send_prompt", {"prompt": "hello", "model": "model-x"}, context={}
    )
    assert result["response"] == "response"
    assert clients[0].messages == ({"role": "user", "content": "hello"},)
    assert clients[0].kwargs["access_token"] == "runtime-token"
    assert clients[0].closed is True
    assert oauth.closed is True


def test_chatgpt_adapter_rejects_unknown_operations_before_authentication():
    adapter = ChatGPTPlanCommunicationAdapter(
        oauth_factory=lambda: pytest.fail("must not authenticate")
    )
    with pytest.raises(ValueError, match="unsupported"):
        adapter.execute("delete_account", {}, context={})


def test_chatgpt_adapter_rejects_invalid_prompt_before_authentication():
    adapter = ChatGPTPlanCommunicationAdapter(
        oauth_factory=lambda: pytest.fail("must not authenticate")
    )
    with pytest.raises(ValueError, match="prompt"):
        adapter.execute("send_prompt", {"prompt": " "}, context={})
