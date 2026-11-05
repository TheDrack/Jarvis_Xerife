from __future__ import annotations

import pytest

from app.application.services.adapter_registry import AdapterRegistry
from app.domain.intelligence.osint import Coordinate, Finding, Host, Signal


class FakeAdapter:
    pass


def test_find_gap_reports_required_and_optional_capabilities_separately() -> None:
    registry = AdapterRegistry()
    adapter = FakeAdapter()
    registry.register("osint.geo.locate", adapter, adapter_id="ipinfo")

    report = registry.find_gap(
        required_capabilities=("osint.geo.locate", "osint.net.resolve"),
        optional_capabilities=("osint.active.scan", "osint.active.signal_capture"),
    )

    assert report.available == ("osint.geo.locate",)
    assert report.missing_required == ("osint.net.resolve",)
    assert report.missing_optional == (
        "osint.active.scan",
        "osint.active.signal_capture",
    )
    assert report.ready is False


def test_find_gap_treats_disabled_active_capabilities_as_optional() -> None:
    registry = AdapterRegistry()
    registry.register("osint.geo.locate", FakeAdapter(), adapter_id="ipinfo")

    report = registry.find_gap(
        required_capabilities=("osint.geo.locate",),
        optional_capabilities=("osint.active.scan",),
    )

    assert report.ready is True
    assert report.missing_required == ()
    assert report.missing_optional == ("osint.active.scan",)


def test_registry_routes_exact_capability_without_provider_coupling() -> None:
    registry = AdapterRegistry()
    first = FakeAdapter()
    second = FakeAdapter()
    registry.register("osint.passive.geo_query", first, adapter_id="censys")
    registry.register("osint.passive.geo_query", second, adapter_id="shodan")

    assert registry.resolve("osint.passive.geo_query") == (first, second)
    assert registry.resolve("osint.passive") == ()


def test_host_requires_explicit_geographic_confidence() -> None:
    with pytest.raises(ValueError):
        Host(ip="203.0.113.10")


def test_signal_is_not_a_host_and_finding_interest_is_unassigned_by_default() -> None:
    signal = Signal(
        kind="wifi",
        identifier="00:11:22:33:44:55",
        geo=Coordinate(lat=-27.1, lon=-48.9, accuracy_m=25, source="kismet"),
        source="kismet",
    )
    finding = Finding(
        entity=signal,
        category="wireless_signal",
        data={"kind": "wifi"},
        source="kismet",
    )

    assert not isinstance(signal, Host)
    assert finding.interest is None

def test_adapter_factory_checks_find_gap_before_creating_duplicate() -> None:
    registry = AdapterRegistry()
    existing = FakeAdapter()
    registry.register("osint.geo.locate", existing, adapter_id="existing")
    created: list[FakeAdapter] = []

    result = registry.create_if_missing(
        "osint.geo.locate",
        adapter_id="replacement",
        factory=lambda: created.append(FakeAdapter()) or created[-1],
    )

    assert result is existing
    assert created == []

def test_multi_capability_factory_checks_find_gap_once_before_creation() -> None:
    registry = AdapterRegistry()
    created: list[FakeAdapter] = []

    adapter = registry.create_for_missing(
        ("osint.geo.locate", "osint.net.resolve"),
        adapter_id="ipinfo",
        factory=lambda: created.append(FakeAdapter()) or created[-1],
    )

    assert len(created) == 1
    assert registry.resolve("osint.geo.locate") == (adapter,)
    assert registry.resolve("osint.net.resolve") == (adapter,)

def test_registry_allows_multiple_providers_for_one_capability_without_duplicates() -> None:
    registry = AdapterRegistry()
    censys = FakeAdapter()
    shodan = FakeAdapter()
    registry.register("osint.passive.geo_query", censys, adapter_id="censys")

    result = registry.create_for_missing(
        ("osint.passive.geo_query",),
        adapter_id="shodan",
        factory=lambda: shodan,
    )

    assert result is shodan
    assert registry.resolve("osint.passive.geo_query") == (censys, shodan)
    assert registry.resolve_bindings("osint.passive.geo_query") == (
        ("censys", censys),
        ("shodan", shodan),
    )
