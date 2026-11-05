from __future__ import annotations

from app.application.services.adapter_registry import AdapterRegistry
from app.application.services.osint_discovery import OSINTDiscoveryService
from app.domain.intelligence.osint import (
    Coordinate,
    GeoLocation,
    Host,
    NetworkRange,
    Signal,
)


class FakeL1:
    def locate(self, ip: str) -> GeoLocation:
        return GeoLocation(
            coordinate=Coordinate(lat=-27.1, lon=-48.9, accuracy_m=50000, source="ipinfo"),
            geo_confidence=0.35,
            connection_type="isp",
        )

    def resolve(self, ip: str) -> NetworkRange:
        return NetworkRange(cidr="203.0.113.0/24", asn=64500, org="Example ISP", country="BR")


class FakePassive:
    def __init__(self, source: str):
        self.source = source
        self.calls = 0

    def query_radius(self, coord, radius_km, filters):
        self.calls += 1
        assert filters["cidrs"] == ["203.0.113.0/24"]
        return [
            Host(
                ip="203.0.113.8",
                ports=(443,),
                geo=Coordinate(lat=-27.1, lon=-48.9, accuracy_m=500, source=self.source),
                geo_confidence=0.8,
                sources=(self.source,),
            )
        ]


class FakeWigle:
    def __init__(self):
        self.calls = 0

    def query_radius(self, coord, radius_km, filters):
        self.calls += 1
        return [
            Signal(
                kind="wifi",
                identifier="AA:BB:CC:DD:EE:FF",
                source="wigle",
            )
        ]


class FakeKismet:
    def __init__(self):
        self.calls = 0

    def capture(self, duration_s):
        self.calls += 1
        return [
            Signal(
                kind="wifi",
                identifier="aa:bb:cc:dd:ee:ff",
                source="kismet",
            )
        ]


def _registry(include_kismet: bool = False):
    registry = AdapterRegistry()
    l1 = FakeL1()
    censys = FakePassive("censys")
    shodan = FakePassive("shodan")
    wigle = FakeWigle()
    registry.register("osint.geo.locate", l1, adapter_id="ipinfo")
    registry.register("osint.net.resolve", l1, adapter_id="ipinfo")
    registry.register("osint.passive.geo_query", censys, adapter_id="censys")
    registry.register("osint.passive.geo_query", shodan, adapter_id="shodan")
    registry.register("osint.passive.signal_query", wigle, adapter_id="wigle")
    kismet = None
    if include_kismet:
        kismet = FakeKismet()
        registry.register("osint.active.signal_capture", kismet, adapter_id="kismet")
    return registry, censys, shodan, wigle, kismet


def test_discover_nearby_runs_mocked_l1_l2_l3_and_fuses_globe_native_findings() -> None:
    registry, censys, shodan, wigle, _ = _registry()
    service = OSINTDiscoveryService(registry=registry)
    report = service.discover_nearby(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        5,
        seed_ip="203.0.113.8",
    )

    assert report.source_health == {
        "ipinfo.geo": True,
        "ipinfo.net": True,
        "censys": True,
        "shodan": True,
        "wigle": True,
    }
    assert censys.calls == shodan.calls == wigle.calls == 1
    host_finding = next(item for item in report.findings if item.category == "host")
    assert host_finding.interest == "confirmed"
    assert host_finding.entity.ip == "203.0.113.8"
    signal_finding = next(item for item in report.findings if item.category == "wireless_signal")
    assert signal_finding.entity.kind == "wifi"


def test_discovery_does_not_query_l2_without_l1_seed_context() -> None:
    registry, censys, shodan, wigle, _ = _registry()
    service = OSINTDiscoveryService(registry=registry)
    report = service.discover_nearby(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        5,
        layers=("L2", "L3"),
    )

    assert censys.calls == shodan.calls == 0
    assert wigle.calls == 1
    assert report.source_health["censys"] is False
    assert report.source_health["shodan"] is False
    assert report.source_health["wigle"] is True


def test_l4_capture_requires_explicit_physical_presence() -> None:
    registry, _, _, _, kismet = _registry(include_kismet=True)
    service = OSINTDiscoveryService(registry=registry)

    denied = service.discover_nearby(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        5,
        layers=("L4",),
        physical_presence=False,
    )
    assert kismet.calls == 0
    assert denied.source_health["kismet"] is False

    allowed = service.discover_nearby(
        Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps"),
        5,
        layers=("L4",),
        physical_presence=True,
    )
    assert kismet.calls == 1
    assert allowed.source_health["kismet"] is True


class RecordingCache:
    def __init__(self):
        self.values = {}
        self.ttls = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ttl_seconds):
        self.values[key] = value
        self.ttls.append(ttl_seconds)


def test_discovery_applies_declared_cache_ttls_and_reuses_results() -> None:
    registry, censys, shodan, wigle, _ = _registry()
    cache = RecordingCache()
    service = OSINTDiscoveryService(registry=registry, cache=cache)
    coordinate = Coordinate(lat=-27.1, lon=-48.9, accuracy_m=10, source="gps")

    first = service.discover_nearby(coordinate, 5, seed_ip="203.0.113.8")
    second = service.discover_nearby(coordinate, 5, seed_ip="203.0.113.8")

    assert [item.entity for item in first.findings] == [
        item.entity for item in second.findings
    ]
    assert [item.interest for item in first.findings] == [
        item.interest for item in second.findings
    ]
    assert censys.calls == shodan.calls == wigle.calls == 1
    assert set(cache.ttls) == {3600, 86400, 7 * 24 * 60 * 60}
    assert any(event["event"] == "cache_hit" for event in second.telemetry)


def test_rate_limiter_is_shared_by_capability_not_provider() -> None:
    import pytest
    from app.application.services.osint_discovery import CapabilityRateLimiter, RateLimitExceeded

    limiter = CapabilityRateLimiter(
        limits={"osint.passive.geo_query": (1, 60)}
    )
    limiter.acquire("osint.passive.geo_query")
    with pytest.raises(RateLimitExceeded):
        limiter.acquire("osint.passive.geo_query")
