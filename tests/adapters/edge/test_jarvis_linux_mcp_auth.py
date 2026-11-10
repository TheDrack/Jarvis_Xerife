"""Authentication tests for the optional Linux MCP HTTP entrypoint."""
import asyncio

from app.adapters.infrastructure.mcp_bearer_auth import BearerAuthMiddleware


TOKEN = "jarvis-test-token-with-at-least-32-bytes-long"


def invoke(app, headers):
    async def run():
        sent = []
        called = []

        async def downstream(scope, receive, send):
            called.append(True)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = BearerAuthMiddleware(downstream, TOKEN)
        scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": headers}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await middleware(scope, receive, send)
        return sent, called

    return asyncio.run(run())


def test_linux_mcp_rejects_missing_bearer_token():
    sent, called = invoke(None, [])

    assert sent[0]["status"] == 401
    assert b"www-authenticate" in dict(sent[0]["headers"])
    assert called == []


def test_linux_mcp_rejects_wrong_bearer_token():
    sent, called = invoke(None, [(b"authorization", b"Bearer wrong-token")])

    assert sent[0]["status"] == 401
    assert called == []


def test_linux_mcp_accepts_exact_bearer_token():
    sent, called = invoke(None, [(b"authorization", f"Bearer {TOKEN}".encode())])

    assert sent[0]["status"] == 200
    assert called == [True]


def test_linux_mcp_rejects_duplicate_authorization_headers():
    sent, called = invoke(
        None,
        [
            (b"authorization", f"Bearer {TOKEN}".encode()),
            (b"authorization", b"Bearer attacker-token"),
        ],
    )

    assert sent[0]["status"] == 401
    assert called == []
