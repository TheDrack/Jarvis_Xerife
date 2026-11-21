"""The capability catalog (C1) and tool manifests (C2) must not disagree.

Both layers answer "which implementation is usable and which comes first?".
These tests fail if the shared vocabulary or the ordering drifts apart again,
and if the repository's real manifest catalog contradicts the Ubuntu reference
catalog.
"""

from typing import Any, Iterable

import pytest

from app.application.services.capability_binding_registry import (
    CapabilityBindingRegistry,
    HostState,
)
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


class TestSharedDeclarationRules:
    def test_duplicate_limitations_are_rejected_by_both_layers(self):
        catalog = CapabilityBindingRegistry()
        catalog.declare_host(
            UBUNTU_SERVER, os_family="ubuntu", state=HostState.ONLINE
        )

        with pytest.raises(ValueError):
            catalog.bind(
                "screen.capture",
                host_ref=UBUNTU_SERVER,
                adapter_id="x11_capture",
                limitations=("requires-display", "requires-display"),
            )

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
                            "host_ref": UBUNTU_SERVER,
                            "adapter_id": "x11_capture",
                            "limitations": [
                                "requires-display",
                                "requires-display",
                            ],
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


def _repository_contradictions(
    catalog: CapabilityBindingRegistry,
    manifests: Iterable[ToolManifest],
) -> tuple[list[str], int]:
    """Compare the real registry against the catalog, declaration by declaration.

    Returns the contradictions found and how many ``availability`` comparisons
    actually ran. The count matters: an earlier version of this check compared
    only capabilities, so a manifest without host alternatives was never
    verified against the catalog at all.
    """
    problems: list[str] = []
    compared = 0

    for manifest in manifests:
        alternatives = manifest.host_implementations
        for capability in manifest.capabilities:
            bindings = catalog.bindings_for(capability)
            if not bindings:
                # ADR-006 R5: the catalog does not map this capability yet; that
                # is declared debt, not a contradiction.
                continue

            if not alternatives:
                # No host alternatives means one implementation and no host
                # dimension. The catalog must still know that adapter for this
                # capability, and must not declare it unusable everywhere.
                same_adapter = [
                    binding
                    for binding in bindings
                    if binding.adapter_id == manifest.adapter_id
                ]
                if not same_adapter:
                    problems.append(
                        f"'{manifest.tool_id}' serves {capability} through "
                        f"'{manifest.adapter_id}', which the catalog does not declare"
                    )
                    continue
                compared += 1
                if not any(binding.usable for binding in same_adapter):
                    problems.append(
                        f"'{manifest.tool_id}' offers '{manifest.adapter_id}' as "
                        f"its only implementation of {capability}, but the catalog "
                        "declares it unavailable on every host"
                    )
                continue

            for alternative in alternatives:
                matches = [
                    binding
                    for binding in bindings
                    if binding.host_ref == alternative.host_ref
                    and binding.adapter_id == alternative.adapter_id
                ]
                if not matches:
                    problems.append(
                        f"'{manifest.tool_id}' declares {capability} through "
                        f"{alternative.host_ref}/{alternative.adapter_id}, which "
                        "the catalog does not declare"
                    )
                    continue
                compared += 1
                for binding in matches:
                    if binding.availability is not alternative.availability:
                        problems.append(
                            f"'{manifest.tool_id}' declares "
                            f"{alternative.host_ref}/{alternative.adapter_id} as "
                            f"'{alternative.availability.value}', but the catalog "
                            f"declares '{binding.availability.value}'"
                        )

    return problems, compared


def _with_alternatives(
    manifest: ToolManifest, alternatives: list[dict[str, Any]]
) -> ToolManifest:
    """Return a validated copy of a real manifest with host alternatives."""
    data = manifest.model_dump()
    data["host_implementations"] = alternatives
    return ToolManifest.model_validate(data)


class TestRepositoryCatalogConsistency:
    """The real ``config/tool_registry.json`` must not contradict the catalog."""

    def test_repository_manifests_agree_with_the_catalog(self):
        problems, compared = _repository_contradictions(
            build_reference_capability_catalog(),
            ToolRegistry.from_file().list_manifests(),
        )

        assert problems == []
        assert compared > 0, (
            "the execution catalog and the reference catalog no longer describe "
            "the same implementation, so this check compares nothing"
        )

    def test_the_check_compares_availability_and_not_only_identity(self):
        """A catalog that declares the real adapter unusable everywhere fails.

        This is the case the previous version could not detect: the catalog
        itself was only asserted to declare *something* usable for a capability,
        never that the implementation the registry actually runs was usable.
        """
        catalog = CapabilityBindingRegistry()
        for host_ref in (UBUNTU_SERVER, UBUNTU_DESKTOP):
            catalog.declare_host(
                host_ref, os_family="ubuntu", state=HostState.ONLINE
            )
            catalog.bind(
                "messaging.send",
                host_ref=host_ref,
                adapter_id="telegram_adapter",
                availability=Availability.UNAVAILABLE,
                limitations=("bot-token-not-provisioned",),
            )

        problems, compared = _repository_contradictions(
            catalog, ToolRegistry.from_file().list_manifests()
        )

        assert compared > 0
        assert any("unavailable on every host" in problem for problem in problems)

    def test_host_alternatives_must_exist_and_match_the_catalog(self):
        catalog = build_reference_capability_catalog()
        manifest = ToolRegistry.from_file().get("telegram.send_message", "1.0.0")
        assert manifest is not None

        undeclared = _with_alternatives(
            manifest,
            [
                {
                    "host_ref": UBUNTU_SERVER,
                    "adapter_id": "x11_capture",
                    "availability": "available",
                }
            ],
        )
        diverging = _with_alternatives(
            manifest,
            [
                {
                    "host_ref": UBUNTU_SERVER,
                    "adapter_id": "telegram_adapter",
                    "availability": "unavailable",
                }
            ],
        )

        for candidate, expected in (
            (undeclared, "catalog does not declare"),
            (diverging, "but the catalog declares 'available'"),
        ):
            problems, _ = _repository_contradictions(catalog, [candidate])
            assert any(
                expected in problem for problem in problems
            ), problems
