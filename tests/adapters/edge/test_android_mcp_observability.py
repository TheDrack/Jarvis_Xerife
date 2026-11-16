from __future__ import annotations

import json

import pytest
from app.adapters.edge.android_mcp_observability import MetadataObservabilityMiddleware


async def _invoke(
    app, *, method="POST", path="/mcp", query=b"token=never-log", body=b"private-prompt"
):
    sent = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": [(b"authorization", b"Bearer super-secret")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8765),
    }
    await app(scope, receive, send)
    return sent


@pytest.mark.asyncio
async def test_middleware_records_metadata_only_for_both_directions(tmp_path):
    log_path = tmp_path / "observability.jsonl"

    async def app(scope, receive, send):
        message = await receive()
        assert message["body"] == b"private-prompt"
        await send(
            {
                "type": "http.response.start",
                "status": 202,
                "headers": [(b"content-length", b"4")],
            }
        )
        await send({"type": "http.response.body", "body": b"safe"})

    middleware = MetadataObservabilityMiddleware(app, log_path=log_path)
    await _invoke(middleware)

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [record["direction"] for record in records] == ["inbound", "outbound"]
    assert records[0]["method"] == "POST"
    assert records[0]["request_bytes"] == len(b"private-prompt")
    assert records[1]["status_code"] == 202
    assert records[1]["response_bytes"] == len(b"safe")
    assert records[0]["request_id"] == records[1]["request_id"]
    serialized = log_path.read_text()
    for forbidden in ("private-prompt", "super-secret", "token=never-log", "12345"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_middleware_logs_route_template_not_dynamic_path(tmp_path):
    log_path = tmp_path / "observability.jsonl"

    async def app(scope, receive, send):
        class Route:
            path = "/v1/sessions/{session_id}"

        scope["route"] = Route()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = MetadataObservabilityMiddleware(app, log_path=log_path)
    await _invoke(
        middleware, method="GET", path="/v1/sessions/user-private-id", body=b""
    )
    serialized = log_path.read_text()
    assert "/v1/sessions/{session_id}" in serialized
    assert "user-private-id" not in serialized


@pytest.mark.asyncio
async def test_middleware_is_fail_open_when_observability_write_fails(
    tmp_path, monkeypatch
):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = MetadataObservabilityMiddleware(
        app, log_path=tmp_path / "missing" / "log.jsonl"
    )
    monkeypatch.setattr(
        middleware,
        "_write_record",
        lambda _record: (_ for _ in ()).throw(OSError("disk")),
    )
    sent = await _invoke(middleware, method="GET", body=b"")
    assert sent[0]["status"] == 200


def test_middleware_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("JARVIS_ANDROID_MCP_OBSERVABILITY", raising=False)
    assert MetadataObservabilityMiddleware.from_environment(lambda *_: None) is None


def test_log_file_is_created_with_owner_only_permissions(tmp_path):
    log_path = tmp_path / "observability.jsonl"
    middleware = MetadataObservabilityMiddleware(lambda *_: None, log_path=log_path)
    middleware._write_record({"direction": "inbound", "request_id": "test"})
    assert log_path.stat().st_mode & 0o777 == 0o600
    assert tmp_path.stat().st_mode & 0o777 == 0o700


def test_middleware_rotates_logs_without_unbounded_growth(tmp_path, monkeypatch):
    from app.adapters.edge import android_mcp_observability as observability

    monkeypatch.setattr(observability, "_MAX_LOG_BYTES", 100)
    log_path = tmp_path / "observability.jsonl"
    middleware = MetadataObservabilityMiddleware(lambda *_: None, log_path=log_path)
    for index in range(8):
        middleware._write_record(
            {"direction": "inbound", "request_id": str(index), "padding": "x" * 32}
        )
    assert log_path.exists()
    assert log_path.stat().st_size <= 100
    assert log_path.with_name(log_path.name + ".1").exists()
    assert len(list(tmp_path.glob("observability.jsonl*"))) <= 4


def test_environment_opt_in_uses_configured_path(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_ANDROID_MCP_OBSERVABILITY", "1")
    monkeypatch.setenv(
        "JARVIS_ANDROID_MCP_OBSERVABILITY_LOG", str(tmp_path / "custom.jsonl")
    )
    middleware = MetadataObservabilityMiddleware.from_environment(lambda *_: None)
    assert middleware is not None
    assert middleware.log_path == tmp_path / "custom.jsonl"
