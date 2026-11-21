"""Host dimension in the execution path (ADR-006 C2)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.tools.contracts import ToolManifest
from app.runtime.toolbox import (
    ToolAuthorizationDecision,
    ToolDispatcher,
    ToolManifest,
    ToolRegistry,
    ToolRequest,
)

DESKTOP = "host:ubuntu-desktop"
SERVER = "host:ubuntu-server"


class _Adapter:
    def __init__(self, adapter_id: str) -> None:
        self.adapter_id = adapter_id

    def capture(self):
        return {"captured": True}


class _Authorizer:
    """Test-only policy: grants for the exact tool/capability/scope in the request."""

    def __init__(self, granted: bool = True) -> None:
        self.granted = granted

    def authorize_tool(self, request, manifest):
        return ToolAuthorizationDecision(
            granted=self.granted,
            principal_id="test-principal",
            session_id="test-session",
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            capability=request.capability or manifest.capabilities[0],
            scope=request.scope,
            operation=manifest.operation,
            approval_id=request.approval_id,
            correlation_id=request.correlation_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )


def _manifest(**overrides):
    data = {
        "tool_id": "screen.capture",
        "version": "1.0.0",
        "description": "Capture the current screen",
        "adapter_id": "portable_screen",
        "operation": "capture",
        "capabilities": ["screen.capture"],
        "host_implementations": [
            {
                "host_ref": SERVER,
                "adapter_id": "headless_screen",
                "availability": "unavailable",
                "limitations": ["requires-graphical-display-session"],
            },
            {"host_ref": DESKTOP, "adapter_id": "x11_screen"},
        ],
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {"captured": {"type": "boolean"}},
            "required": ["captured"],
            "additionalProperties": False,
        },
    }
    data.update(overrides)
    return data


def _dispatcher(*, granted: bool = True, events=None, calls=None):
    calls = calls if calls is not None else []
    registry = ToolRegistry([_manifest()])

    def resolver(adapter_id):
        calls.append(adapter_id)
        return _Adapter(adapter_id)

    return (
        ToolDispatcher(
            registry,
            resolver=resolver,
            authorizer=_Authorizer(granted=granted),
            event_sink=events.append if events is not None else None,
        ),
        calls,
    )


def _request(**overrides) -> ToolRequest:
    data = {
        "tool_id": "screen.capture",
        "tool_version": "1.0.0",
        "capability": "screen.capture",
    }
    data.update(overrides)
    return ToolRequest(**data)


class TestHostSelection:
    def test_picks_the_available_host_and_records_the_implementation(self):
        events = []
        dispatcher, calls = _dispatcher(events=events)

        result = asyncio.run(dispatcher.dispatch_async(_request()))

        assert result.success is True
        assert result.adapter_id == "x11_screen"
        assert result.host_ref == DESKTOP
        assert result.capability == "screen.capture"
        assert calls == ["x11_screen"]
        assert events[0].adapter_id == "x11_screen"
        assert events[0].host_ref == DESKTOP
        assert events[0].capability == "screen.capture"

    def test_requested_host_selects_that_implementation(self):
        dispatcher, calls = _dispatcher()

        result = asyncio.run(
            dispatcher.dispatch_async(_request(host_ref=DESKTOP))
        )

        assert result.success is True
        assert calls == ["x11_screen"]

    def test_unavailable_host_fails_explicitly_without_fallback(self):
        dispatcher, calls = _dispatcher()

        result = asyncio.run(
            dispatcher.dispatch_async(_request(host_ref=SERVER))
        )

        assert result.success is False
        assert result.status == "rejected"
        assert result.error_code == "capability_unavailable"
        assert result.host_ref == SERVER
        assert "requires-graphical-display-session" in (result.error_message or "")
        assert calls == []

    def test_host_that_does_not_declare_the_tool_is_rejected(self):
        dispatcher, calls = _dispatcher()

        result = asyncio.run(
            dispatcher.dispatch_async(_request(host_ref="host:ubuntu-laptop"))
        )

        assert result.success is False
        assert result.error_code == "capability_unavailable"
        assert result.host_ref == "host:ubuntu-laptop"
        assert calls == []

    def test_authorization_still_decides_before_host_selection(self):
        dispatcher, calls = _dispatcher(granted=False)

        result = asyncio.run(
            dispatcher.dispatch_async(_request(host_ref=DESKTOP))
        )

        assert result.success is False
        assert result.error_code == "authorization_denied"
        assert calls == []


class TestManifestHostDeclarations:
    def test_rejects_duplicate_host_and_adapter(self):
        data = _manifest()
        data["host_implementations"].append(
            {"host_ref": DESKTOP, "adapter_id": "x11_screen"}
        )

        with pytest.raises(ValidationError):
            ToolManifest.model_validate(data)

    def test_rejects_invalid_host_reference(self):
        data = _manifest()
        data["host_implementations"] = [
            {"host_ref": "ubuntu-desktop", "adapter_id": "x11_screen"}
        ]

        with pytest.raises(ValidationError):
            ToolManifest.model_validate(data)

    def test_rejects_objective_identifier_as_capability(self):
        data = _manifest(capabilities=["objective:CAP-001"])

        with pytest.raises(ValidationError):
            ToolManifest.model_validate(data)

def test_process_idempotency_is_scoped_to_requested_host():
    data = _manifest(
        host_implementations=[
            {"host_ref": SERVER, "adapter_id": "headless_screen"},
            {"host_ref": DESKTOP, "adapter_id": "x11_screen"},
        ],
        idempotency="supported",
    )
    calls = []
    dispatcher = ToolDispatcher(
        ToolRegistry([data]),
        resolver=lambda adapter_id: calls.append(adapter_id) or _Adapter(adapter_id),
        authorizer=_Authorizer(),
    )

    desktop_result = asyncio.run(
        dispatcher.dispatch_async(
            _request(host_ref=DESKTOP, idempotency_key="same-key")
        )
    )
    server_result = asyncio.run(
        dispatcher.dispatch_async(
            _request(host_ref=SERVER, idempotency_key="same-key")
        )
    )

    assert desktop_result.success is True
    assert desktop_result.adapter_id == "x11_screen"
    assert server_result.success is True
    assert server_result.status == "succeeded"
    assert server_result.adapter_id == "headless_screen"
    assert server_result.host_ref == SERVER
    assert calls == ["x11_screen", "headless_screen"]
