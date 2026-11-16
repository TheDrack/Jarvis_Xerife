import json

import pytest
from app.communication import (
    CommunicationCapture,
    CommunicationRegistry,
    CommunicationReplay,
    CommunicationRequest,
)


class FakeAdapter:
    adapter_id = "fake.http"

    def __init__(self):
        self.calls = []

    def execute(self, operation, payload, *, context):
        self.calls.append((operation, payload, context))
        return {"status": "ok", "echo": payload}


def test_registry_rejects_duplicate_adapter_ids():
    registry = CommunicationRegistry()
    adapter = FakeAdapter()
    registry.register(adapter)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeAdapter())
    assert registry.resolve("fake.http") is adapter


def test_capture_redacts_secrets_and_persists_replayable_shape(tmp_path):
    path = tmp_path / "captures.jsonl"
    capture = CommunicationCapture(path)
    request = CommunicationRequest(
        adapter_id="fake.http",
        protocol="https",
        operation="send_message",
        payload={
            "text": "hello",
            "nested": {"access_token": "secret-value", "apiKey": "camel-secret"},
            "callback": "https://example.test/cb?access_token=query-secret",
        },
        metadata={"Authorization": "Bearer private", "trace": "abc"},
    )

    record = capture.record(request, {"status": "ok"})
    persisted = json.loads(path.read_text().strip())

    assert record.capture_id
    assert persisted["request"]["payload"]["text"] == "hello"
    assert persisted["request"]["payload"]["nested"]["access_token"] == "[REDACTED]"
    assert persisted["request"]["payload"]["nested"]["apiKey"] == "[REDACTED]"
    assert "query-secret" not in path.read_text()
    assert "camel-secret" not in path.read_text()
    assert persisted["request"]["metadata"]["Authorization"] == "[REDACTED]"
    assert "secret-value" not in path.read_text()
    assert "private" not in path.read_text()


def test_replay_requires_authorizer_and_uses_override_payload(tmp_path):
    capture = CommunicationCapture(tmp_path / "captures.jsonl")
    request = CommunicationRequest(
        adapter_id="fake.http",
        protocol="https",
        operation="send_message",
        payload={"text": "original"},
    )
    record = capture.record(request, {"status": "ok"})
    adapter = FakeAdapter()
    registry = CommunicationRegistry([adapter])

    replay = CommunicationReplay(capture, registry)
    with pytest.raises(PermissionError):
        replay.execute(record.capture_id, overrides={"text": "changed"})

    replay = CommunicationReplay(
        capture,
        registry,
        authorizer=lambda _record, _payload, _context, approval: approval == "approved",
    )
    result = replay.execute(
        record.capture_id, overrides={"text": "changed"}, approval_ref="approved"
    )
    assert result == {"status": "ok", "echo": {"text": "changed"}}
    assert adapter.calls[0][1] == {"text": "changed"}
    with pytest.raises(ValueError, match="runtime context"):
        replay.execute(
            record.capture_id,
            overrides={"apiKey": "should-not-enter-payload"},
            approval_ref="approved",
        )


def test_capture_rejects_non_json_payload(tmp_path):
    capture = CommunicationCapture(tmp_path / "captures.jsonl")
    request = CommunicationRequest(
        adapter_id="fake.http",
        protocol="https",
        operation="send_message",
        payload={"bad": object()},
    )
    with pytest.raises(ValueError, match="JSON-compatible"):
        capture.record(request, {"status": "ok"})
