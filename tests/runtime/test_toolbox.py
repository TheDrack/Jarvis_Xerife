"""Contract and dispatch tests for the Universal Toolbox."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.application.security.capability_authorizer import (
    CapabilityAuthorizer as LegacyCapabilityAuthorizer,
)
from app.runtime.toolbox import (
    RateLimitPolicy,
    ToolAuthorizationDecision,
    ToolchainManifest,
    ToolchainRunner,
    ToolDispatcher,
    ToolManifest,
    ToolRegistry,
    ToolResult,
)


class CapabilityAuthorizer(LegacyCapabilityAuthorizer):
    """Test-only policy adapter; production must provide a trusted approval verifier."""

    def authorize_tool(self, request, manifest):
        approval_id = request.approval_id
        self.authorize(
            user="test-principal",
            capability_name=manifest.authorization_capability,
            payload={
                "scope": request.scope,
                "human_confirmed": bool(approval_id),
            },
        )
        return ToolAuthorizationDecision(
            granted=True,
            principal_id="test-principal",
            session_id="test-session",
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            capability=request.capability or manifest.capabilities[0],
            scope=request.scope,
            operation=manifest.operation,
            approval_id=approval_id,
            correlation_id=request.correlation_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )


@pytest.fixture
def registry():
    return ToolRegistry(
        [
            {
                "tool_id": "sample.read",
                "version": "1.0.0",
                "description": "Read sample data",
                "capability": "sample.read",
                "adapter_id": "sample_adapter",
                "operation": "read",
                "authorization_capability": "sample_adapter",
                "input_schema": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                    "additionalProperties": False,
                },
            },
            {
                "tool_id": "sample.write",
                "version": "1.0.0",
                "description": "Write sample data",
                "capability": "sample.write",
                "adapter_id": "sample_adapter",
                "operation": "write",
                "authorization_capability": "sample_adapter",
                "risk_level": "active",
                "idempotency_mode": "process",
                "requires_idempotency_key": True,
                "input_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            },
        ]
    )


class SampleAdapter:
    def read(self, key):
        return {"key": key}

    def write(self, value):
        return {"written": value}


def make_dispatcher(registry, events=None):
    authorizer = CapabilityAuthorizer(
        allowlist={"sample_adapter"}, require_confirmation_for=set()
    )
    return ToolDispatcher(
        registry,
        resolver=lambda adapter_id: (
            SampleAdapter() if adapter_id == "sample_adapter" else None
        ),
        authorizer=authorizer,
        event_sink=(events.append if events is not None else None),
    )


def test_manifest_rejects_private_adapter_operation_name():
    with pytest.raises(ValueError, match="public adapter method"):
        ToolManifest(
            tool_id="sample.invalid",
            version="1.0.0",
            description="invalid operation",
            capability="sample.invalid",
            adapter_id="sample_adapter",
            operation="__class__",
            authorization_capability="sample_adapter",
        )


def test_manifest_rejects_non_object_input_schema():
    with pytest.raises(ValueError, match="object root"):
        ToolManifest(
            tool_id="sample.invalid",
            version="1.0.0",
            description="invalid",
            capability="sample.invalid",
            adapter_id="sample_adapter",
            operation="read",
            authorization_capability="sample_adapter",
            input_schema={"type": "string"},
        )


def test_registry_rejects_duplicate_tool_ids(registry):
    with pytest.raises(ValueError, match="already registered"):
        registry.register(registry.get("sample.read"))


def test_registry_indexes_capabilities(registry):
    assert [
        item.tool_id for item in registry.find_by_capability("sample.read")
    ] == ["sample.read"]


def test_dispatch_validates_schema_before_resolving_adapter(registry):
    resolver_calls = []
    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda adapter_id: resolver_calls.append(adapter_id),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    result = dispatcher.dispatch(
        {"tool_id": "sample.read", "arguments": {"unknown": 1}}
    )
    assert result.status == "rejected"
    assert result.error_code == "invalid_arguments"
    assert resolver_calls == []


def test_dispatch_rejects_unknown_tool(registry):
    result = make_dispatcher(registry).dispatch({"tool_id": "sample.missing"})
    assert result.status == "rejected"
    assert result.error_code == "tool_not_found"


def test_dispatch_requires_explicit_version_when_tool_has_multiple_versions(
    registry,
):
    original = registry.get("sample.read", "1.0.0")
    registry.register(original.model_copy(update={"version": "1.1.0"}))
    result = make_dispatcher(registry).dispatch(
        {"tool_id": "sample.read", "arguments": {"key": "status"}}
    )
    assert result.status == "rejected"
    assert result.error_code == "tool_version_required"


def test_dispatch_executes_read_only_tool_and_emits_audit(registry):
    events = []
    result = make_dispatcher(registry, events).dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "status"},
            "caller": "test-agent",
            "scope": "local",
            "correlation_id": "corr-1",
        }
    )
    assert result.success is True
    assert result.output == {"key": "status"}
    assert len(events) == 1
    assert events[0].tool_id == "sample.read"
    assert events[0].correlation_id == "corr-1"


def test_side_effect_requires_confirmation(registry):
    result = make_dispatcher(registry).dispatch(
        {
            "tool_id": "sample.write",
            "arguments": {"value": "hello"},
            "idempotency_key": "write-1",
        }
    )
    assert result.status == "rejected"
    assert result.error_code == "approval_reference_required"


def test_side_effect_requires_idempotency_key(registry):
    result = make_dispatcher(registry).dispatch(
        {
            "tool_id": "sample.write",
            "arguments": {"value": "hello"},
            "approval_id": "test-approval",
        }
    )
    assert result.error_code == "idempotency_key_required"


def test_process_idempotency_prevents_duplicate_side_effect(registry):
    calls = []

    class CountingAdapter:
        def write(self, value):
            calls.append(value)
            return {"written": value}

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: CountingAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    request = {
        "tool_id": "sample.write",
        "arguments": {"value": "once"},
        "approval_id": "test-approval",
        "idempotency_key": "same-key",
    }
    first = dispatcher.dispatch(request)
    second = dispatcher.dispatch(request)
    assert first.success is True
    assert second.status == "duplicate"
    assert calls == ["once"]


def test_process_idempotency_isolated_by_tool_version_and_capability(registry):
    calls = []

    class CountingAdapter:
        def write(self, value):
            calls.append(value)
            return {"written": value}

    original = registry.get("sample.write", "1.0.0")
    multi_capability = original.model_copy(
        update={
            "capabilities": ("sample.write", "sample.write.secondary"),
        }
    )
    registry.register(multi_capability, replace=True)
    registry.register(multi_capability.model_copy(update={"version": "1.1.0"}))
    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: CountingAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    first = dispatcher.dispatch(
        {
            "tool_id": "sample.write",
            "tool_version": "1.0.0",
            "capability": "sample.write",
            "arguments": {"value": "v1"},
            "approval_id": "approval-v1",
            "idempotency_key": "shared-key",
        }
    )
    second = dispatcher.dispatch(
        {
            "tool_id": "sample.write",
            "tool_version": "1.0.0",
            "capability": "sample.write.secondary",
            "arguments": {"value": "v2"},
            "approval_id": "approval-v2",
            "idempotency_key": "shared-key",
        }
    )
    third = dispatcher.dispatch(
        {
            "tool_id": "sample.write",
            "tool_version": "1.1.0",
            "capability": "sample.write",
            "arguments": {"value": "v3"},
            "approval_id": "approval-v3",
            "idempotency_key": "shared-key",
        }
    )

    assert first.success is True
    assert second.success is True
    assert third.success is True
    assert calls == ["v1", "v2", "v3"]


def test_authorization_denial_blocks_execution(registry):
    calls = []
    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: calls.append("resolved"),
        authorizer=CapabilityAuthorizer(
            allowlist=set(), require_confirmation_for=set()
        ),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "status"},
        }
    )
    assert result.error_code == "authorization_denied"
    assert calls == []


def test_async_adapter_is_supported(registry):
    class AsyncAdapter:
        async def read(self, key):
            await asyncio.sleep(0)
            return {"key": key}

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: AsyncAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    result = asyncio.run(
        dispatcher.dispatch_async(
            {
                "tool_id": "sample.read",
                "arguments": {"key": "status"},
            }
        )
    )
    assert result.success is True
    assert result.output == {"key": "status"}


def test_registry_loads_checked_in_manifests():
    registry = ToolRegistry.from_file()
    assert {item.tool_id for item in registry.list_tools()} == {
        "telegram.get_updates",
        "telegram.send_message",
        "drive.upload_backup",
        "network.get_interfaces",
        "network.discover_devices",
    }
    assert (
        registry.get("telegram.send_message").requires_idempotency_key is True
    )
    assert (
        registry.get("drive.upload_backup").operation == "upload_backup_scoped"
    )


def test_legacy_authorizer_requires_confirmation_for_explicitly_allowlisted_drive():
    authorizer = CapabilityAuthorizer(allowlist={"drive_uploader"})
    with pytest.raises(PermissionError, match="confirma"):
        authorizer.authorize("agent", "drive_uploader", {})
    assert (
        authorizer.authorize(
            "agent", "drive_uploader", {"human_confirmed": True}
        )
        is True
    )


def test_checked_in_telegram_manifest_dispatches_adapter_method():
    calls = []

    class FakeTelegram:
        def can_execute(self, context=None):
            return True

        def send_message_scoped(self, text, chat_id=None):
            if chat_id != "test-chat":
                return {
                    "success": False,
                    "error_code": "telegram_chat_scope_mismatch",
                }
            calls.append((text, chat_id))
            return {"ok": True, "result": {"message_id": 7}}

    dispatcher = ToolDispatcher(
        ToolRegistry.from_file(),
        resolver=lambda adapter_id: FakeTelegram(),
        authorizer=CapabilityAuthorizer(),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "telegram.send_message",
            "arguments": {
                "text": "Jarvis toolbox test",
                "chat_id": "test-chat",
            },
            "caller": "integration-test",
            "approval_id": "test-approval",
            "idempotency_key": "telegram-test-1",
        }
    )

    assert result.success is True
    assert result.output["result"]["message_id"] == 7
    assert result.provider == "Telegram Bot API"
    assert result.tool_version == "1.0.0"
    assert calls == [("Jarvis toolbox test", "test-chat")]


def test_checked_in_drive_manifest_dispatches_atomic_adapter_method():
    calls = []

    class FakeDrive:
        def can_execute(self, context=None):
            return True

        def upload_backup_scoped(self, context):
            calls.append(context)
            return {
                "success": True,
                "file_id": "drive-file-1",
                "file_name": "backup.txt",
            }

    dispatcher = ToolDispatcher(
        ToolRegistry.from_file(),
        resolver=lambda adapter_id: FakeDrive(),
        authorizer=CapabilityAuthorizer(allowlist={"drive_uploader"}),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "drive.upload_backup",
            "arguments": {"context": {"result": {"file_path": "backup.txt"}}},
            "caller": "integration-test",
            "approval_id": "test-approval",
            "idempotency_key": "drive-test-1",
        }
    )

    assert result.success is True
    assert result.output["file_id"] == "drive-file-1"
    assert calls == [{"result": {"file_path": "backup.txt"}}]


def test_checked_in_drive_manifest_does_not_accept_failed_adapter_result():
    class FakeDrive:
        def can_execute(self, context=None):
            return True

        def upload_backup_scoped(self, context):
            return {"success": False, "error_code": "file_not_found"}

    dispatcher = ToolDispatcher(
        ToolRegistry.from_file(),
        resolver=lambda adapter_id: FakeDrive(),
        authorizer=CapabilityAuthorizer(allowlist={"drive_uploader"}),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "drive.upload_backup",
            "arguments": {"context": {}},
            "approval_id": "test-approval",
            "idempotency_key": "drive-failed-1",
        }
    )

    assert result.success is False
    assert result.error_code == "file_not_found"


def test_audit_sink_persists_only_event_metadata(tmp_path):
    from app.runtime.toolbox import JsonlToolAuditSink, ToolExecutionEvent

    path = tmp_path / "audit" / "tool-events.jsonl"
    sink = JsonlToolAuditSink(path)
    event = ToolExecutionEvent(
        request_id="req-1",
        tool_id="telegram.send_message",
        tool_version="1.0.0",
        caller="test-agent",
        scope="local",
        status="succeeded",
        provider="Telegram Bot API",
        request_fingerprint="sha256:test-fingerprint",
        cost_units=1,
        error_code=None,
    )
    sink(event)
    record = json.loads(path.read_text(encoding="utf-8").strip())

    assert record["tool_id"] == "telegram.send_message"
    assert record["provider"] == "Telegram Bot API"
    assert record["request_fingerprint"] == "sha256:test-fingerprint"
    assert "arguments" not in record
    assert "output" not in record
    assert "token" not in json.dumps(record).lower()


def test_idempotency_key_cannot_be_reused_with_different_arguments(registry):
    calls = []

    class CountingAdapter:
        def write(self, value):
            calls.append(value)
            return {"written": value}

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: CountingAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    first = dispatcher.dispatch(
        {
            "tool_id": "sample.write",
            "arguments": {"value": "first"},
            "approval_id": "test-approval",
            "idempotency_key": "key-conflict",
        }
    )
    second = dispatcher.dispatch(
        {
            "tool_id": "sample.write",
            "arguments": {"value": "different"},
            "approval_id": "test-approval",
            "idempotency_key": "key-conflict",
        }
    )

    assert first.success is True
    assert second.error_code == "idempotency_conflict"
    assert calls == ["first"]


def test_unknown_side_effect_outcome_is_cached_to_prevent_replay(registry):
    calls = []

    class UncertainAdapter:
        def write(self, value):
            calls.append(value)
            raise TimeoutError("simulated provider timeout")

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: UncertainAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    request = {
        "tool_id": "sample.write",
        "arguments": {"value": "send once"},
        "approval_id": "test-approval",
        "idempotency_key": "uncertain-key",
    }
    first = dispatcher.dispatch(request)
    second = dispatcher.dispatch(request)

    assert first.error_code == "execution_outcome_unknown"
    assert second.status == "duplicate"
    assert second.error_code == "execution_outcome_unknown"
    assert calls == ["send once"]


def test_cached_idempotent_result_still_requires_authorization(registry):
    calls = []
    authorizer = CapabilityAuthorizer(
        allowlist={"sample_adapter"}, require_confirmation_for=set()
    )

    class CountingAdapter:
        def write(self, value):
            calls.append(value)
            return {"written": value}

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: CountingAdapter(),
        authorizer=authorizer,
    )
    request = {
        "tool_id": "sample.write",
        "arguments": {"value": "protected"},
        "approval_id": "test-approval",
        "idempotency_key": "auth-before-cache",
    }
    assert dispatcher.dispatch(request).success is True

    authorizer.remove_from_allowlist("sample_adapter")
    denied = dispatcher.dispatch(request)
    assert denied.error_code == "authorization_denied"
    assert calls == ["protected"]


def test_concurrent_duplicate_is_reported_in_progress(registry):
    from threading import Event, Thread

    started = Event()
    release = Event()
    calls = []

    class BlockingAdapter:
        def write(self, value):
            calls.append(value)
            started.set()
            release.wait(timeout=3)
            return {"written": value}

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: BlockingAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    request = {
        "tool_id": "sample.write",
        "arguments": {"value": "concurrent"},
        "approval_id": "test-approval",
        "idempotency_key": "concurrent-key",
    }
    first_result = []
    worker = Thread(
        target=lambda: first_result.append(dispatcher.dispatch(request))
    )
    worker.start()
    assert started.wait(timeout=2)

    second = dispatcher.dispatch(request)
    release.set()
    worker.join(timeout=3)

    assert second.status == "in_progress"
    assert first_result and first_result[0].success is True
    assert calls == ["concurrent"]


def test_dispatch_rejects_scope_outside_manifest_allowlist(registry):
    resolver_calls = []
    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda adapter_id: resolver_calls.append(adapter_id),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "status"},
            "scope": "remote:unapproved-host",
        }
    )

    assert result.error_code == "scope_denied"
    assert resolver_calls == []


def test_manifest_rejects_empty_scope_allowlist():
    with pytest.raises(ValueError, match="allowed_scopes"):
        ToolManifest(
            tool_id="sample.no_scope",
            version="1.0.0",
            description="No scopes",
            capability="sample.read",
            adapter_id="sample_adapter",
            operation="read",
            authorization_capability="sample_adapter",
            allowed_scopes=[],
            input_schema={"type": "object"},
        )


def test_dispatch_validates_adapter_output_schema(registry):
    class BadAdapter:
        def read(self, key):
            return {"key": 123}

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: BadAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "status"},
        }
    )

    assert result.success is False
    assert result.error_code == "invalid_output"


def test_registry_rejects_invalid_schema_version(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": "v1", "tools": []}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="schema_version"):
        ToolRegistry.from_file(path)


def test_adapter_precondition_failure_is_not_reported_as_authorization_denial(
    registry,
):
    class NotReadyAdapter:
        def can_execute(self, context=None):
            return False

        def read(self, key):
            raise AssertionError("Operation must not be called")

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: NotReadyAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "status"},
        }
    )

    assert result.error_code == "adapter_not_ready"


def test_local_rate_limit_returns_retry_after(registry):
    read_tool = registry.get("sample.read").model_copy(
        update={"rate_limit": RateLimitPolicy(requests=1, window_seconds=60)}
    )
    limited_registry = ToolRegistry([read_tool])
    dispatcher = ToolDispatcher(
        limited_registry,
        resolver=lambda _: SampleAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    request = {"tool_id": "sample.read", "arguments": {"key": "status"}}

    assert dispatcher.dispatch(request).success is True
    limited = dispatcher.dispatch(request)

    assert limited.error_code == "rate_limited"
    assert limited.retryable is True
    assert limited.retry_after_seconds > 0


def test_read_only_timeout_is_retryable(registry):
    read_tool = registry.get("sample.read").model_copy(
        update={"timeout_seconds": 0.01}
    )
    limited_registry = ToolRegistry([read_tool])

    class SlowAdapter:
        def read(self, key):
            import time

            time.sleep(0.05)
            return {"key": key}

    dispatcher = ToolDispatcher(
        limited_registry,
        resolver=lambda _: SlowAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "slow"},
        }
    )

    assert result.error_code == "tool_timeout"
    assert result.retryable is True


def test_active_timeout_is_unknown_and_not_replayed(registry):
    write_tool = registry.get("sample.write").model_copy(
        update={"timeout_seconds": 0.01}
    )
    limited_registry = ToolRegistry([write_tool])
    calls = []

    class SlowAdapter:
        def write(self, value):
            import time

            calls.append(value)
            time.sleep(0.05)
            return {"written": value}

    dispatcher = ToolDispatcher(
        limited_registry,
        resolver=lambda _: SlowAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    request = {
        "tool_id": "sample.write",
        "arguments": {"value": "slow-side-effect"},
        "approval_id": "test-approval",
        "idempotency_key": "slow-side-effect-1",
    }
    first = dispatcher.dispatch(request)
    second = dispatcher.dispatch(request)

    assert first.error_code == "execution_outcome_unknown"
    assert second.status == "duplicate"
    assert second.error_code == "execution_outcome_unknown"
    assert calls == ["slow-side-effect"]


def test_toolchain_retries_only_retryable_read_only_tools():
    registry = ToolRegistry(
        [
            {
                "tool_id": "sample.read",
                "version": "1.0.0",
                "description": "Read",
                "capability": "sample.read",
                "adapter_id": "sample",
                "operation": "read",
                "authorization_capability": "sample",
                "input_schema": {"type": "object"},
                "risk_level": "read_only",
            },
            {
                "tool_id": "sample.write",
                "version": "1.0.0",
                "description": "Write",
                "capability": "sample.write",
                "adapter_id": "sample",
                "operation": "write",
                "authorization_capability": "sample",
                "input_schema": {"type": "object"},
                "risk_level": "active",
                "idempotency_mode": "process",
                "requires_idempotency_key": True,
            },
        ]
    )

    class RetryDispatcher:
        def __init__(self):
            self.registry = registry
            self.calls = []

        def dispatch(self, request):
            self.calls.append(request.tool_id)
            if len(self.calls) == 1:
                return ToolResult(
                    tool_id=request.tool_id,
                    request_id=request.request_id,
                    success=False,
                    status="failed",
                    retryable=True,
                )
            return ToolResult(
                tool_id=request.tool_id,
                request_id=request.request_id,
                success=True,
                status="succeeded",
                output={},
            )

    dispatcher = RetryDispatcher()
    chain = ToolchainManifest.model_validate(
        {
            "toolchain_id": "retry.read",
            "version": "1.0.0",
            "description": "Retry a safe read-only tool",
            "steps": [
                {
                    "step_id": "read",
                    "tool_id": "sample.read",
                    "max_attempts": 2,
                    "retry_backoff_seconds": 0,
                }
            ],
        }
    )
    result = ToolchainRunner(dispatcher).run(chain)

    assert result.status == "succeeded"
    assert dispatcher.calls == ["sample.read", "sample.read"]


def test_toolchain_budget_stops_before_overspending():
    registry = ToolRegistry(
        [
            {
                "tool_id": "sample.read",
                "version": "1.0.0",
                "description": "Read",
                "capability": "sample.read",
                "adapter_id": "sample",
                "operation": "read",
                "authorization_capability": "sample",
                "input_schema": {"type": "object"},
                "cost_units": 2,
            },
            {
                "tool_id": "sample.other",
                "version": "1.0.0",
                "description": "Other",
                "capability": "sample.other",
                "adapter_id": "sample",
                "operation": "other",
                "authorization_capability": "sample",
                "input_schema": {"type": "object"},
                "cost_units": 2,
            },
        ]
    )

    class BudgetDispatcher:
        def __init__(self):
            self.registry = registry
            self.calls = []

        def dispatch(self, request):
            self.calls.append(request.tool_id)
            return ToolResult(
                tool_id=request.tool_id,
                request_id=request.request_id,
                success=True,
                status="succeeded",
                output={},
            )

    dispatcher = BudgetDispatcher()
    chain = ToolchainManifest.model_validate(
        {
            "toolchain_id": "budget.test",
            "version": "1.0.0",
            "description": "Budget test",
            "budget_units": 3,
            "continue_on_error": True,
            "steps": [
                {"step_id": "first", "tool_id": "sample.read"},
                {"step_id": "second", "tool_id": "sample.other"},
            ],
        }
    )
    result = ToolchainRunner(dispatcher).run(chain)

    assert result.status == "partial"
    assert dispatcher.calls == ["sample.read"]
    assert result.step_results["second"].error_code == "budget_exceeded"


def test_circuit_breaker_opens_and_recovers_for_provider_failures(registry):
    import time

    read_tool = registry.get("sample.read").model_copy(
        update={
            "circuit_breaker_threshold": 2,
            "circuit_breaker_reset_seconds": 0.05,
        }
    )
    limited_registry = ToolRegistry([read_tool])
    calls = []

    class FlakyAdapter:
        def read(self, key):
            calls.append(key)
            if len(calls) <= 2:
                raise ConnectionError("provider unavailable")
            return {"key": key}

    dispatcher = ToolDispatcher(
        limited_registry,
        resolver=lambda _: FlakyAdapter(),
        authorizer=CapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )
    request = {"tool_id": "sample.read", "arguments": {"key": "status"}}

    first = dispatcher.dispatch(request)
    second = dispatcher.dispatch(request)
    blocked = dispatcher.dispatch(request)
    time.sleep(0.06)
    recovered = dispatcher.dispatch(request)

    assert first.retryable is True
    assert second.retryable is True
    assert blocked.error_code == "circuit_open"
    assert blocked.retryable is True
    assert recovered.success is True
    assert calls == ["status", "status", "status"]


def test_evidence_record_preserves_source_provenance():
    from app.runtime.toolbox import EvidenceRecord

    evidence = EvidenceRecord(
        source_id="gdelt:event:123",
        provider="GDELT",
        uri="https://example.invalid/events/123",
        publisher="Public source",
        license="CC-BY",
        content_hash="sha256:abc123",
        transformations=["html_to_text", "deduplicate"],
        corroborates=["evidence-456"],
        confidence=0.92,
    )

    assert evidence.source_id == "gdelt:event:123"
    assert evidence.provider == "GDELT"
    assert evidence.transformations == ["html_to_text", "deduplicate"]
    assert evidence.confidence == 0.92
    assert evidence.collected_at.tzinfo is not None


def test_external_tool_manifest_requires_provider():
    with pytest.raises(ValueError, match="provider"):
        ToolManifest(
            tool_id="external.lookup",
            version="1.0.0",
            description="External lookup",
            capability="external.lookup",
            adapter_id="external_adapter",
            operation="lookup",
            authorization_capability="external_adapter",
            origin="third_party",
            input_schema={"type": "object"},
        )


def test_legacy_capability_authorizer_cannot_authorize_tool_dispatch(registry):
    calls = []
    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: calls.append("resolved"),
        authorizer=LegacyCapabilityAuthorizer(
            allowlist={"sample_adapter"}, require_confirmation_for=set()
        ),
    )

    result = dispatcher.dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "status"},
            "caller": "forged-admin",
        }
    )

    assert result.error_code == "authorization_denied"
    assert calls == []


def test_authorization_decision_must_match_exact_tool_and_version(registry):
    calls = []

    class MismatchedPolicy:
        def authorize_tool(self, request, manifest):
            return ToolAuthorizationDecision(
                granted=True,
                principal_id="authenticated-user",
                session_id="session-1",
                tool_id="sample.write",
                tool_version="9.9.9",
                capability="sample.write",
                scope=request.scope,
                operation=manifest.operation,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
            )

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: calls.append("resolved"),
        authorizer=MismatchedPolicy(),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "sample.read",
            "arguments": {"key": "status"},
        }
    )

    assert result.error_code == "authorization_denied"
    assert calls == []


def test_active_approval_reference_must_be_verified_and_bound(registry):
    calls = []

    class WrongApprovalPolicy:
        def authorize_tool(self, request, manifest):
            return ToolAuthorizationDecision(
                granted=True,
                principal_id="authenticated-user",
                session_id="session-1",
                tool_id=manifest.tool_id,
                tool_version=manifest.version,
                capability=manifest.capability,
                scope=request.scope,
                operation=manifest.operation,
                approval_id="different-approval",
                correlation_id=request.correlation_id,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
            )

    dispatcher = ToolDispatcher(
        registry,
        resolver=lambda _: calls.append("resolved"),
        authorizer=WrongApprovalPolicy(),
    )
    result = dispatcher.dispatch(
        {
            "tool_id": "sample.write",
            "arguments": {"value": "must-not-run"},
            "approval_id": "caller-supplied-approval",
            "idempotency_key": "approval-binding-1",
        }
    )

    assert result.error_code == "authorization_denied"
    assert calls == []


def test_runtime_registry_is_the_canonical_domain_registry():
    from app.domain.tools.registry import ToolRegistry as DomainToolRegistry

    assert ToolRegistry is DomainToolRegistry


def test_canonical_manifest_supports_non_object_output_schema():
    manifest = ToolManifest(
        tool_id="sample.read",
        version="1.0.0",
        description="Read a list",
        adapter_id="sample_adapter",
        operation="list_items",
        capabilities=("sample.list",),
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        output_schema={"type": "array", "items": {"type": "string"}},
        execution_mode="read_only",
        idempotency="not_applicable",
    )

    assert manifest.output_schema["type"] == "array"
