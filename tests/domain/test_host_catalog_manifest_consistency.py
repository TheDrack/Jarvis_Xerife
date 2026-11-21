"""The capability catalog (C1) and tool manifests (C2) must not disagree.

Both layers answer "which implementation is usable and which comes first?".
These tests fail if the shared vocabulary or the ordering drifts apart again,
and if the repository's real manifest catalog contradicts the Ubuntu reference
catalog.
"""

from typing import Any

import pytest

from app.application.services.reference_host_catalog import (
    UBUNTU_DESKTOP,
    UBUNTU_SERVER,
    build_reference_capability_catalog,
)
from app.domain.tools.contracts import ToolManifest
from app.domain.tools.host_selection import (
    Availability,
    GapReason,
    implementation_order_key,
)
from app.runtime.toolbox.dispatcher import (
    ToolDispatcher,
    _CapabilityUnavailableError,
)
from app.runtime.toolbox.registry import ToolRegistry

#: Capabilities the reference catalog declares on both Ubuntu hosts.
SHARED_CAPABILITIES = (
    "screen.capture",
    "host.observe.resources",
    "messaging.send",
)


def _manifest_for(capability: str, catalog) -> ToolManifest:
    """Declare exactly what the catalog declares, as a tool manifest."""
    bindings = catalog.bindings_for(capability)
    assert bindings, f"catalog declares no binding for {capability}"
    return ToolManifest.model_validate(
        {
            "tool_id": "host.consistency.probe",
            "version": "1.0.0",
            "description": "Manifest mirroring the capability catalog.",
            "adapter_id": bindings[0].adapter_id,
            "operation": "probe",
            "capabilities": [capability],
            "host_implementations": [
                {
                    "host_ref": binding.host_ref,
                    "adapter_id": binding.adapter_id,
                    "availability": binding.availability.value,
                    "limitations": list(binding.limitations),
                }
                for binding in bindings
            ],
        }
    )


def _declared_order(item: Any) -> tuple[int, int, str, str]:
    """Sort manifest host alternatives with the shared ordering."""
    return implementation_order_key(
        availability=item.availability,
        adapter_id=item.adapter_id,
        host_ref=item.host_ref,
    )


def _dispatcher(manifest: ToolManifest) -> ToolDispatcher:
    # Only _select_implementation is exercised; no adapter or policy is resolved.
    return ToolDispatcher(
        ToolRegistry([manifest]), resolver=lambda _: None, authorizer=object()
    )


class TestSharedVocabulary:
    def test_manifest_and_catalog_read_the_same_availability(self):
        catalog = build_reference_capability_catalog()

        for capability in SHARED_CAPABILITIES:
            manifest = _manifest_for(capability, catalog)
            declared = {
                item.host_ref: item for item in manifest.host_implementations
            }
            for binding in catalog.bindings_for(capability):
                item = declared[binding.host_ref]
                assert item.availability is binding.availability
                assert item.availability.usable is binding.usable

    def test_manifest_rejects_an_unknown_availability(self):
        with pytest.raises(ValueError):
            ToolManifest.model_validate(
                {
                    "tool_id": "host.consistency.probe",
                    "version": "1.0.0",
                    "description": "Manifest mirroring the capability catalog.",
                    "adapter_id": "x11_capture",
                    "operation": "probe",
                    "capabilities": ["screen.capture"],
                    "host_implementations": [
                        {
                            "host_ref": UBUNTU_DESKTOP,
                            "adapter_id": "x11_capture",
                            "availability": "mostly_fine",
                        }
                    ],
                }
            )


class TestSharedOrdering:
    def test_manifest_order_matches_catalog_order(self):
        catalog = build_reference_capability_catalog()

        for capability in SHARED_CAPABILITIES:
            manifest = _manifest_for(capability, catalog)
            from_catalog = [
                (binding.host_ref, binding.adapter_id)
                for binding in catalog.bindings_for(capability)
            ]
            from_manifest = [
                (item.host_ref, item.adapter_id)
                for item in sorted(
                    manifest.host_implementations, key=_declared_order
                )
            ]
            assert from_manifest == from_catalog

    def test_dispatcher_agrees_with_catalog_on_every_declared_host(self):
        catalog = build_reference_capability_catalog()

        for capability in SHARED_CAPABILITIES:
            manifest = _manifest_for(capability, catalog)
            dispatcher = _dispatcher(manifest)

            for host_ref in (UBUNTU_SERVER, UBUNTU_DESKTOP):
                resolution = catalog.resolve_capability(capability, host_ref)
                if resolution.available:
                    chosen = dispatcher._select_implementation(
                        manifest, host_ref
                    )
                    assert chosen.adapter_id == resolution.best.adapter_id
                    assert chosen.host_ref == resolution.best.host_ref
                    assert chosen.limitations == resolution.best.limitations
                else:
                    with pytest.raises(_CapabilityUnavailableError) as raised:
                        dispatcher._select_implementation(manifest, host_ref)
                    assert raised.value.reason == resolution.gap.reason.value

    def test_headless_ubuntu_server_is_unavailable_in_both_layers(self):
        catalog = build_reference_capability_catalog()
        manifest = _manifest_for("screen.capture", catalog)

        resolution = catalog.resolve_capability("screen.capture", UBUNTU_SERVER)
        with pytest.raises(_CapabilityUnavailableError) as raised:
            _dispatcher(manifest)._select_implementation(manifest, UBUNTU_SERVER)

        assert resolution.gap.reason is GapReason.IMPLEMENTATION_UNAVAILABLE
        assert raised.value.reason == resolution.gap.reason.value
        assert snapshot_availability(manifest) == (
            Availability.AVAILABLE,
            Availability.UNAVAILABLE,
        )


def snapshot_availability(manifest: ToolManifest) -> tuple[Availability, ...]:
    """Availability per declared host, in the order the catalog resolves them."""
    return tuple(
        item.availability
        for item in sorted(manifest.host_implementations, key=_declared_order)
    )


class TestRepositoryCatalogConsistency:
    """The real ``config/tool_registry.json`` must not contradict the catalog."""

    def test_repository_manifests_agree_with_the_catalog(self):
        catalog = build_reference_capability_catalog()
        registry = ToolRegistry.from_file()
        checked = 0

        for manifest in registry.list_manifests():
            for capability in manifest.capabilities:
                bindings = catalog.bindings_for(capability)
                if not bindings:
                    # The catalog does not cover this capability yet (ADR-006 R5).
                    continue
                checked += 1
                assert any(
                    binding.usable for binding in bindings
                ), f"catalog declares {capability} but nothing usable for it"

                for item in manifest.host_implementations:
                    assert catalog.host(item.host_ref) is not None, (
                        f"manifest '{manifest.tool_id}' declares undeclared "
                        f"host {item.host_ref}"
                    )
                    shared = [
                        binding
                        for binding in bindings
                        if binding.host_ref == item.host_ref
                        and binding.adapter_id == item.adapter_id
                    ]
                    for binding in shared:
                        assert binding.availability is item.availability

        assert checked > 0, "no manifest capability is covered by the catalog"
