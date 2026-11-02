"""Contract and registry tests for the Universal Tool Registry foundation."""

import pytest
from pydantic import ValidationError

from app.domain.tools import (
    DuplicateToolManifestError,
    HealthPolicy,
    ToolManifest,
    ToolRegistry,
)


def make_manifest(**overrides):
    data = {
        "tool_id": "telegram.send_message",
        "version": "1.0.0",
        "description": "Send a Telegram message.",
        "adapter_id": "telegram_adapter",
        "operation": "send_message",
        "provider": "telegram",
        "capabilities": ["telegram.message.send"],
        "input_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        "output_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"message_id": {"type": "string"}},
            "required": ["message_id"],
            "additionalProperties": False,
        },
        "permissions": ["telegram:send"],
        "execution_mode": "active_bounded",
        "credential_refs": ["env://TELEGRAM_TOKEN"],
        "side_effects": ["send_message"],
    }
    data.update(overrides)
    return ToolManifest.model_validate(data)


def test_manifest_accepts_versioned_provider_neutral_metadata():
    manifest = make_manifest()

    assert manifest.tool_id == "telegram.send_message"
    assert manifest.version == "1.0.0"
    assert manifest.capabilities == ("telegram.message.send",)
    assert manifest.credential_refs == ("env://TELEGRAM_TOKEN",)


@pytest.mark.parametrize(
    "overrides",
    [
        {"tool_id": "Telegram.Send"},
        {"tool_id": "telegram send"},
        {"version": "1.0"},
        {"version": "v1"},
        {"version": "1.0.0-01"},
        {"version": "1.0.0-alpha..1"},
        {"capabilities": []},
        {"capabilities": ["telegram.send", "telegram.send"]},
        {"credential_refs": ["TELEGRAM_TOKEN=plain-secret-value"]},
        {"credential_refs": ["https://example.com/token"]},
        {"credential_refs": ["secret://provider/../token"]},
        {"credential_refs": ["secret://provider//token"]},
        {"terms_uri": "file:///etc/passwd"},
        {"input_schema": {"type": "string"}},
    ],
)
def test_manifest_rejects_invalid_contract_metadata(overrides):
    with pytest.raises(ValidationError):
        make_manifest(**overrides)


def test_read_only_manifest_cannot_declare_side_effects():
    with pytest.raises(
        ValidationError, match="read_only tools cannot declare side effects"
    ):
        make_manifest(
            execution_mode="read_only",
            permissions=[],
            side_effects=["send_message"],
            credential_refs=[],
        )


def test_active_manifest_requires_declared_permissions():
    with pytest.raises(ValidationError, match="must declare permissions"):
        make_manifest(permissions=[])


def test_periodic_health_policy_requires_interval():
    with pytest.raises(ValidationError, match="requires interval_seconds"):
        HealthPolicy(mode="periodic")


def test_registry_resolves_exact_tool_version():
    registry = ToolRegistry()
    registered = registry.register(make_manifest())

    assert registered.tool_id == "telegram.send_message"
    assert registry.get("telegram.send_message", "1.0.0") is not None
    assert registry.get("telegram.send_message", "2.0.0") is None
    assert len(registry) == 1


def test_registry_rejects_duplicate_tool_version_unless_replace_is_explicit():
    registry = ToolRegistry()
    registry.register(make_manifest())

    with pytest.raises(DuplicateToolManifestError):
        registry.register(make_manifest())

    replacement = make_manifest(description="Updated description.")
    registry.register(replacement, replace=True)

    assert (
        registry.get("telegram.send_message", "1.0.0").description
        == "Updated description."
    )
    assert len(registry) == 1


def test_registry_capability_lookup_is_exact_not_substring():
    registry = ToolRegistry(
        [
            make_manifest(),
            make_manifest(
                tool_id="telegram.message.history",
                adapter_id="telegram_adapter",
                capabilities=["telegram.message.read"],
                permissions=["telegram:read"],
                side_effects=[],
                credential_refs=[],
                execution_mode="read_only",
            ),
        ]
    )

    matches = registry.find_by_capability("telegram.message.send")

    assert [item.tool_id for item in matches] == ["telegram.send_message"]
    assert registry.find_by_capability("telegram.message") == ()


def test_registry_defensively_copies_nested_schema_data():
    manifest = make_manifest()
    registry = ToolRegistry()
    registry.register(manifest)

    manifest.input_schema["properties"]["injected"] = {"type": "string"}
    stored = registry.get("telegram.send_message", "1.0.0")
    assert "injected" not in stored.input_schema["properties"]

    stored.input_schema["properties"]["mutated"] = {"type": "string"}
    reloaded = registry.get("telegram.send_message", "1.0.0")
    assert "mutated" not in reloaded.input_schema["properties"]


def test_registry_list_is_stably_sorted():
    registry = ToolRegistry(
        [
            make_manifest(
                tool_id="zeta.lookup",
                adapter_id="zeta_adapter",
                capabilities=["zeta.lookup"],
                permissions=[],
                side_effects=[],
                credential_refs=[],
                execution_mode="read_only",
            ),
            make_manifest(
                tool_id="alpha.lookup",
                adapter_id="alpha_adapter",
                capabilities=["alpha.lookup"],
                permissions=[],
                side_effects=[],
                credential_refs=[],
                execution_mode="read_only",
            ),
        ]
    )

    assert [item.tool_id for item in registry.list_manifests()] == [
        "alpha.lookup",
        "zeta.lookup",
    ]


def test_registry_requires_version_when_multiple_versions_exist():
    registry = ToolRegistry(
        [
            make_manifest(),
            make_manifest(version="2.0.0"),
        ]
    )

    with pytest.raises(ValueError, match="tool_version is required"):
        registry.get_unique("telegram.send_message")