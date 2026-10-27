import pytest

from app.domain.models.capability_alias_registry import (
    Capability,
    CapabilityAliasRegistry,
    CapabilityDenied,
    DuplicateAliasError,
    UnknownAliasError,
)


def make_registry(*, requires_confirmation=False):
    registry = CapabilityAliasRegistry()
    registry.register_capability(
        Capability(
            capability_id="desktop.inspect",
            description="Inspect current desktop state",
            handler=lambda payload: {"observed": payload.get("target", "desktop")},
            required_permission="desktop.read",
            requires_confirmation=requires_confirmation,
        )
    )
    registry.register_alias("SCOPE-01", "desktop.inspect", "inspect_desktop")
    return registry


def test_alias_resolves_to_canonical_capability():
    registry = make_registry()
    binding, capability = registry.resolve("SCOPE-01")
    assert binding.capability_id == "desktop.inspect"
    assert capability.required_permission == "desktop.read"


def test_unknown_alias_and_duplicate_alias_fail_closed():
    registry = make_registry()
    with pytest.raises(UnknownAliasError):
        registry.resolve("unknown")
    with pytest.raises(DuplicateAliasError):
        registry.register_alias("SCOPE-01", "desktop.inspect", "another_intent")


def test_authorization_uses_canonical_id_and_audits_alias():
    registry = make_registry()
    seen = []
    result = registry.execute(
        "SCOPE-01",
        {"target": "task_scheduler"},
        authorize=lambda capability_id, permission: (
            capability_id == "desktop.inspect" and permission == "desktop.read"
        ),
        audit=seen.append,
    )
    assert result == {"observed": "task_scheduler"}
    assert seen[-1]["alias"] == "SCOPE-01"
    assert seen[-1]["capability_id"] == "desktop.inspect"
    assert seen[-1]["status"] == "success"


def test_denied_execution_is_audited_and_handler_is_not_run():
    called = []
    registry = CapabilityAliasRegistry()
    registry.register_capability(
        Capability("dangerous.operation", "test", lambda _: called.append(True))
    )
    registry.register_alias("VEIL-09", "dangerous.operation", "test_intent")
    events = []
    with pytest.raises(CapabilityDenied):
        registry.execute(
            "VEIL-09",
            authorize=lambda *_: False,
            audit=events.append,
        )
    assert called == []
    assert events[-1]["status"] == "denied"
    assert events[-1]["capability_id"] == "dangerous.operation"


def test_confirmation_requirement_cannot_be_bypassed_by_alias():
    registry = make_registry(requires_confirmation=True)
    events = []
    with pytest.raises(CapabilityDenied, match="Explicit confirmation"):
        registry.execute(
            "SCOPE-01",
            authorize=lambda *_: True,
            audit=events.append,
            confirmed=False,
        )
    assert events[-1]["status"] == "confirmation_required"


def test_describe_returns_canonical_mapping():
    registry = make_registry()
    item = registry.describe()[0]
    assert item["alias"] == "SCOPE-01"
    assert item["capability_id"] == "desktop.inspect"
    assert item["required_permission"] == "desktop.read"
