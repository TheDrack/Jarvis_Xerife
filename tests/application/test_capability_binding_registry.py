"""Tests for the capability -> host -> implementation layer (ADR-006 C1)."""

import pytest

from app.application.services.adapter_registry import AdapterRegistry
from app.application.services.capability_binding_registry import (
    Availability,
    CapabilityBindingRegistry,
    GapReason,
    HostState,
    NamespaceViolation,
    normalize_capability_id,
    validate_host_ref,
)
from app.application.services.reference_host_catalog import (
    UBUNTU_DESKTOP,
    UBUNTU_SERVER,
    build_reference_capability_catalog,
)

DESKTOP = "host:ubuntu-desktop"
SERVER = "host:ubuntu-server"


def _two_host_catalog() -> CapabilityBindingRegistry:
    """Two hosts; only the desktop host declares screen capture."""
    catalog = CapabilityBindingRegistry()
    catalog.declare_host(DESKTOP, os_family="ubuntu", state=HostState.ONLINE)
    catalog.declare_host(
        SERVER, os_family="ubuntu", state=HostState.ONLINE, limitations=("headless",)
    )
    catalog.bind(
        "screen.capture", host_ref=DESKTOP, adapter_id="hardware_controller"
    )
    catalog.bind(
        "host.observe.resources",
        host_ref=DESKTOP,
        adapter_id="psutil_host_adapter",
    )
    catalog.bind(
        "host.observe.resources",
        host_ref=SERVER,
        adapter_id="psutil_host_adapter",
    )
    return catalog


class TestCapabilityNamespace:
    def test_normalizes_canonical_prefix(self):
        assert normalize_capability_id("screen.capture") == "capability:screen.capture"
        assert (
            normalize_capability_id("capability:screen.capture")
            == "capability:screen.capture"
        )

    def test_objective_identifiers_are_not_capabilities(self):
        with pytest.raises(NamespaceViolation):
            normalize_capability_id("objective:CAP-001")

    def test_rejects_invalid_identifier(self):
        with pytest.raises(ValueError):
            normalize_capability_id("Screen Capture")

    def test_validates_host_reference(self):
        assert validate_host_ref("host:ubuntu-server") == "host:ubuntu-server"
        with pytest.raises(ValueError):
            validate_host_ref("ubuntu-server")


class TestResolution:
    def test_unknown_capability_is_an_explicit_gap(self):
        catalog = _two_host_catalog()
        resolution = catalog.resolve_capability("screen.record")

        assert resolution.available is False
        assert resolution.candidates == ()
        assert resolution.gap is not None
        assert resolution.gap.reason is GapReason.NO_IMPLEMENTATION

    def test_host_without_the_capability_reports_the_gap(self):
        catalog = _two_host_catalog()
        resolution = catalog.resolve_capability("screen.capture", SERVER)

        assert resolution.available is False
        assert resolution.best is None
        assert resolution.gap is not None
        assert resolution.gap.reason is GapReason.CAPABILITY_NOT_DECLARED
        assert resolution.gap.host_ref == SERVER

    def test_unknown_host_reports_the_gap(self):
        catalog = _two_host_catalog()
        resolution = catalog.resolve_capability("screen.capture", "host:ubuntu-laptop")

        assert resolution.available is False
        assert resolution.gap is not None
        assert resolution.gap.reason is GapReason.HOST_UNKNOWN

    def test_unknown_host_state_reports_an_explicit_gap(self):
        catalog = CapabilityBindingRegistry()
        catalog.declare_host(SERVER, os_family="ubuntu")
        catalog.bind("screen.capture", host_ref=SERVER, adapter_id="x11_capture")

        resolution = catalog.resolve_capability("screen.capture", SERVER)

        assert resolution.available is False
        assert resolution.gap is not None
        assert resolution.gap.reason is GapReason.HOST_STATE_UNKNOWN

    def test_unverified_hosts_are_not_offered_without_a_host_selection(self):
        catalog = CapabilityBindingRegistry()
        catalog.declare_host(DESKTOP, os_family="ubuntu")
        catalog.bind("screen.capture", host_ref=DESKTOP, adapter_id="x11_capture")

        resolution = catalog.resolve_capability("screen.capture")

        assert resolution.available is False
        assert resolution.gap is not None
        assert resolution.gap.reason is GapReason.HOST_STATE_UNKNOWN

    def test_offline_host_reports_the_gap(self):
        catalog = CapabilityBindingRegistry()
        catalog.declare_host(
            SERVER, os_family="ubuntu", state=HostState.OFFLINE
        )
        catalog.bind("screen.capture", host_ref=SERVER, adapter_id="x11_capture")

        resolution = catalog.resolve_capability("screen.capture", SERVER)

        assert resolution.available is False
        assert resolution.gap is not None
        assert resolution.gap.reason is GapReason.HOST_OFFLINE

    def test_offline_host_is_skipped_when_no_host_is_requested(self):
        catalog = _two_host_catalog()
        catalog.declare_host(
            "host:ubuntu-laptop", os_family="ubuntu", state=HostState.OFFLINE
        )
        catalog.bind(
            "screen.capture", host_ref="host:ubuntu-laptop", adapter_id="wayland_capture"
        )

        resolution = catalog.resolve_capability("screen.capture")

        assert resolution.available is True
        assert {item.host_ref for item in resolution.candidates} == {DESKTOP}

    def test_unavailable_implementation_keeps_its_limitation_for_diagnosis(self):
        catalog = build_reference_capability_catalog(host_state=HostState.ONLINE)

        resolution = catalog.resolve_capability("screen.capture", UBUNTU_SERVER)

        assert resolution.available is False
        assert resolution.gap is not None
        assert resolution.gap.reason is GapReason.IMPLEMENTATION_UNAVAILABLE
        assert "requires-graphical-display-session" in resolution.gap.detail
        assert resolution.candidates[0].limitations == (
            "requires-graphical-display-session",
        )

    def test_orders_available_before_unavailable_regardless_of_insertion(self):
        catalog = CapabilityBindingRegistry()
        catalog.declare_host(DESKTOP, os_family="ubuntu", state=HostState.ONLINE)
        catalog.declare_host(SERVER, os_family="ubuntu", state=HostState.ONLINE)
        catalog.bind(
            "screen.capture",
            host_ref=SERVER,
            adapter_id="headless_capture",
            availability=Availability.UNAVAILABLE,
            limitations=("requires-display",),
        )
        catalog.bind(
            "screen.capture", host_ref=DESKTOP, adapter_id="x11_capture"
        )

        resolution = catalog.resolve_capability("screen.capture")

        assert resolution.available is True
        assert [item.host_ref for item in resolution.candidates] == [DESKTOP]

    def test_priority_breaks_ties_deterministically(self):
        catalog = CapabilityBindingRegistry()
        catalog.declare_host(
            DESKTOP, os_family="ubuntu", state=HostState.ONLINE
        )
        catalog.declare_host(
            SERVER, os_family="ubuntu", state=HostState.ONLINE
        )
        catalog.bind(
            "screen.capture",
            host_ref=SERVER,
            adapter_id="server_capture",
            priority=10,
        )
        catalog.bind(
            "screen.capture", host_ref=DESKTOP, adapter_id="desktop_capture"
        )

        first = catalog.resolve_capability("screen.capture")
        second = catalog.resolve_capability("capability:screen.capture")

        assert first.to_dict() == second.to_dict()
        assert [item.adapter_id for item in first.candidates] == [
            "server_capture",
            "desktop_capture",
        ]

    def test_requested_host_returns_only_that_host(self):
        catalog = _two_host_catalog()
        resolution = catalog.resolve_capability("host.observe.resources", SERVER)

        assert resolution.available is True
        assert resolution.best is not None
        assert resolution.best.host_ref == SERVER
        assert len(resolution.candidates) == 1


class TestDeclarations:
    def test_binding_requires_a_declared_host(self):
        catalog = CapabilityBindingRegistry()

        with pytest.raises(ValueError):
            catalog.bind("screen.capture", host_ref=DESKTOP, adapter_id="x11_capture")

    def test_duplicate_host_and_duplicate_binding_are_rejected(self):
        catalog = _two_host_catalog()

        with pytest.raises(ValueError):
            catalog.declare_host(DESKTOP, os_family="ubuntu")
        with pytest.raises(ValueError):
            catalog.bind(
                "screen.capture",
                host_ref=DESKTOP,
                adapter_id="hardware_controller",
            )

    def test_inherits_capability_level_gap_detection(self):
        catalog = _two_host_catalog()
        assert isinstance(catalog, AdapterRegistry)

        catalog.register("osint.lookup", object(), adapter_id="osint_adapter")
        gap = catalog.find_gap(required_capabilities=("osint.lookup",))

        assert gap.ready is True
        assert len(catalog.resolve("osint.lookup")) == 1

    def test_coverage_report_lists_implementations_per_host(self):
        catalog = _two_host_catalog()
        report = catalog.coverage_report()

        by_capability = {
            item["capability_id"]: item for item in report["capabilities"]
        }
        screen = by_capability["capability:screen.capture"]
        assert screen["implementations"] == 1
        assert screen["hosts"] == {DESKTOP: ["hardware_controller"]}
        assert screen["usable_hosts"] == [DESKTOP]

        resources = by_capability["capability:host.observe.resources"]
        assert resources["implementations"] == 2
        assert resources["usable_hosts"] == [DESKTOP, SERVER]
        assert [host["host_ref"] for host in report["hosts"]] == [DESKTOP, SERVER]


class TestReferenceCatalog:
    def test_ubuntu_hosts_declare_the_same_capabilities(self):
        catalog = build_reference_capability_catalog()

        server = catalog.host(UBUNTU_SERVER)
        desktop = catalog.host(UBUNTU_DESKTOP)

        assert server is not None and server.os_family == "ubuntu"
        assert desktop is not None and desktop.os_family == "ubuntu"
        assert server.state is HostState.UNKNOWN
        assert desktop.state is HostState.UNKNOWN

    def test_screen_capture_resolves_differently_per_ubuntu_host(self):
        catalog = build_reference_capability_catalog(host_state=HostState.ONLINE)

        desktop = catalog.resolve_capability("screen.capture", UBUNTU_DESKTOP)
        server = catalog.resolve_capability("screen.capture", UBUNTU_SERVER)

        assert desktop.available is True
        assert desktop.best is not None
        assert desktop.best.adapter_id == "hardware_controller"
        assert desktop.best.limitations == ("captures-only-the-current-x11-session",)

        assert server.available is False
        assert server.gap is not None
        assert server.gap.reason is GapReason.IMPLEMENTATION_UNAVAILABLE

    def test_telemetry_is_available_on_both_ubuntu_hosts(self):
        catalog = build_reference_capability_catalog(host_state=HostState.ONLINE)

        resolution = catalog.resolve_capability("host.observe.resources")

        assert resolution.available is True
        assert {item.host_ref for item in resolution.candidates} == {
            UBUNTU_SERVER,
            UBUNTU_DESKTOP,
        }
        assert {item.policy_class for item in resolution.candidates} == {"observe"}
