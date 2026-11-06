from __future__ import annotations

import pytest

from app.application.services.adapter_registry import OSINTAdapterRegistry
from app.application.services.graph_expander_setup import (
    DEFAULT_RATE_LIMITS,
    configure_graph_expanders,
    get_graph_expander_registry,
)
from app.application.services.osint_adapter_setup import configure_osint_adapters
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.registry import ExpanderRegistry, RateLimit, RateLimitExceeded
from app.domain.intelligence.osint import GeoLocation, NetworkRange

FULL_ENV = {
    "CENSYS_API_TOKEN": "censys-test",
    "SHODAN_API_KEY": "shodan-test",
    "WIGLE_USERNAME": "wigle-test",
    "WIGLE_API_TOKEN": "wigle-token",
}
SEED = Node(type=NodeType.IP, selector="203.0.113.9", scope_id="case-3")


def _adapters(environment: dict[str, str]) -> OSINTAdapterRegistry:
    return configure_osint_adapters(
        OSINTAdapterRegistry(), environment=environment
    )


class _StubIPInfo:
    def locate(self, ip: str) -> GeoLocation:
        return GeoLocation(
            coordinate=None,
            geo_confidence=0.0,
            connection_type=None,
            is_proxy=False,
        )

    def resolve(self, ip: str) -> NetworkRange:
        return NetworkRange(
            cidr="203.0.113.0/24", asn=64500, org="Example ISP", country="BR"
        )


def _stub_adapters() -> OSINTAdapterRegistry:
    registry = OSINTAdapterRegistry()
    stub = _StubIPInfo()
    registry.register("osint.geo.locate", stub, adapter_id="ipinfo")
    registry.register("osint.net.resolve", stub, adapter_id="ipinfo")
    return registry


def test_without_optional_credentials_only_ipinfo_expanders_are_registered() -> None:
    registry = configure_graph_expanders(
        ExpanderRegistry(), adapters=_adapters({})
    )

    assert [expander.spec.name for expander in registry.all()] == ["asn", "ipinfo"]
    assert registry.rate_limit("osint.ip.enrich") == DEFAULT_RATE_LIMITS[
        "osint.ip.enrich"
    ]
    # Capability sem provider configurado não ganha janela artificial.
    assert registry.rate_limit("osint.passive.geo_query") is None


def test_every_configured_provider_gets_an_expander() -> None:
    registry = configure_graph_expanders(
        ExpanderRegistry(), adapters=_adapters(FULL_ENV)
    )

    assert [expander.spec.name for expander in registry.all()] == [
        "asn",
        "censys",
        "ipinfo",
        "shodan",
        "wigle",
    ]
    assert [
        expander.spec.name
        for expander in registry.find_expanders(NodeType.COORDINATE)
    ] == ["censys", "shodan", "wigle"]
    assert registry.rate_limit("osint.passive.geo_query") == DEFAULT_RATE_LIMITS[
        "osint.passive.geo_query"
    ]


def test_ipinfo_is_injected_under_both_geo_and_network_capabilities() -> None:
    registry = configure_graph_expanders(
        ExpanderRegistry(), adapters=_adapters({})
    )
    capabilities = {
        expander.spec.capability for expander in registry.all()
    }

    assert capabilities == {"osint.ip.enrich", "osint.net.resolve"}
    assert registry.find_expanders(NodeType.IP) != ()


def test_injected_rate_limits_stop_a_capability() -> None:
    registry = ExpanderRegistry(clock=lambda: 0.0)
    configure_graph_expanders(
        registry,
        adapters=_stub_adapters(),
        rate_limits={"osint.ip.enrich": RateLimit(max_calls=1, period_seconds=60)},
    )
    expander = registry.find_expanders(NodeType.IP, ["osint.ip.enrich"])[0]

    expander.expand(SEED)
    with pytest.raises(RateLimitExceeded):
        expander.expand(SEED)


def test_lazy_registry_reuses_the_shared_osint_adapters(monkeypatch) -> None:
    from app.application.services import graph_expander_setup as setup

    monkeypatch.setattr(setup, "get_osint_registry", lambda: _adapters(FULL_ENV))
    monkeypatch.setattr(setup, "_registry", None)

    first = setup.get_graph_expander_registry()

    assert first is setup.get_graph_expander_registry()
    assert {expander.spec.name for expander in first.all()} == {
        "asn",
        "censys",
        "ipinfo",
        "shodan",
        "wigle",
    }
