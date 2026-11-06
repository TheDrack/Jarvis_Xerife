from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.adapters.infrastructure.osint.censys_adapter import CensysAdapter
from app.adapters.infrastructure.osint.expanders import (
    AsnExpander,
    CensysExpander,
    IPInfoExpander,
    ShodanExpander,
    WigleExpander,
)
from app.adapters.infrastructure.osint.ipinfo_adapter import IPInfoAdapter
from app.adapters.infrastructure.osint.shodan_adapter import ShodanAdapter
from app.adapters.infrastructure.osint.wigle_adapter import WigleAdapter
from app.domain.graph.edges import PivotType
from app.domain.graph.expander import ExpansionCost
from app.domain.graph.nodes import Node, NodeType
from app.domain.intelligence.osint import Coordinate, Host

SCOPE = "case-3"
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "osint"
SEED_COORDINATE = Node(
    type=NodeType.COORDINATE,
    selector="-27.1,-48.9",
    scope_id=SCOPE,
    attributes={"cidrs": ["203.0.113.0/24"], "radius_km": 5},
)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(payload: dict, requests: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _ipinfo(fixture: str) -> IPInfoAdapter:
    return IPInfoAdapter(client=_client(_fixture(fixture)))


def _censys() -> CensysAdapter:
    return CensysAdapter(
        client=_client(_fixture("censys_hosts.json")),
        token_provider=lambda: "censys-token",
    )


def _shodan() -> ShodanAdapter:
    return ShodanAdapter(
        client=_client(_fixture("shodan_hosts.json")),
        api_key_provider=lambda: "shodan-key",
    )


def _wigle(requests: list[httpx.Request] | None = None) -> WigleAdapter:
    return WigleAdapter(
        client=_client(_fixture("wigle_signals.json"), requests),
        username_provider=lambda: "user",
        token_provider=lambda: "token",
    )


def test_ipinfo_expander_propagates_geo_confidence_and_asn() -> None:
    adapter = _ipinfo("ipinfo_ip.json")
    expander = IPInfoExpander(adapter, adapter)

    expansion = expander.expand(
        Node(type=NodeType.IP, selector="203.0.113.9", scope_id=SCOPE)
    )

    assert expander.spec.capability == "osint.ip.enrich"
    assert expander.spec.cost is ExpansionCost.ZERO
    coordinate = next(
        node for node in expansion.nodes if node.type is NodeType.COORDINATE
    )
    assert coordinate.selector == "-27.100000,-48.900000"
    assert coordinate.attributes["geo_confidence"] == 0.35
    asn = next(node for node in expansion.nodes if node.type is NodeType.ASN)
    assert asn.selector == "as64500"
    assert asn.attributes["org_name"] == "Example ISP"
    assert {edge.pivot for edge in expansion.edges} == {
        PivotType.GEO_LOCATED,
        PivotType.ASN_OWNER,
    }
    # ORG é declarado como efeito observável, mas nunca construído pelo adapter.
    assert NodeType.ORG in expander.spec.produces
    assert not [node for node in expansion.nodes if node.type is NodeType.ORG]


def test_ipinfo_expander_caps_geo_confidence_for_mobile_or_proxy() -> None:
    adapter = _ipinfo("ipinfo_mobile.json")
    expansion = IPInfoExpander(adapter, adapter).expand(
        Node(type=NodeType.IP, selector="203.0.113.10", scope_id=SCOPE)
    )

    coordinate = next(
        node for node in expansion.nodes if node.type is NodeType.COORDINATE
    )
    assert coordinate.attributes["geo_confidence"] <= 0.3
    assert coordinate.attributes["is_proxy"] is True


def test_censys_expander_produces_hosts_with_geo_confidence() -> None:
    expansion = CensysExpander(_censys()).expand(SEED_COORDINATE)

    host = next(node for node in expansion.nodes if node.type is NodeType.HOST)
    assert host.selector == "203.0.113.8"
    assert host.attributes["geo_confidence"] == 0.55
    assert host.attributes["ports"] == [443]
    assert any(edge.pivot is PivotType.GEO_LOCATED for edge in expansion.edges)


def test_shodan_expander_produces_hosts_with_geo_confidence() -> None:
    expansion = ShodanExpander(_shodan()).expand(SEED_COORDINATE)

    host = next(node for node in expansion.nodes if node.type is NodeType.HOST)
    assert host.selector == "203.0.113.8"
    assert host.attributes["geo_confidence"] == 0.6
    assert host.attributes["ports"] == [443, 8443]
    assert any(edge.pivot is PivotType.GEO_LOCATED for edge in expansion.edges)


def test_censys_and_shodan_are_interchangeable_in_the_pipeline() -> None:
    censys = CensysExpander(_censys())
    shodan = ShodanExpander(_shodan())

    assert censys.spec.capability == shodan.spec.capability
    assert censys.spec.produces == shodan.spec.produces
    assert censys.spec.cost is shodan.spec.cost

    def pipeline(expander) -> set[NodeType]:
        return {node.type for node in expander.expand(SEED_COORDINATE).nodes}

    assert pipeline(censys) == pipeline(shodan) == {NodeType.HOST, NodeType.COORDINATE}


def test_censys_requires_authorised_cidrs() -> None:
    coordinate_only = Node(
        type=NodeType.COORDINATE, selector="-27.1,-48.9", scope_id=SCOPE
    )

    assert CensysExpander(_censys()).expand(coordinate_only).nodes == ()


def test_every_host_from_passive_intel_carries_geo_confidence() -> None:
    class _NoGeoIntel:
        def query_radius(self, coord: Coordinate, radius_km: float, filters: dict):
            return (Host(ip="198.51.100.7", geo_confidence=0.0, sources=("stub",)),)

    expansion = CensysExpander(_NoGeoIntel()).expand(SEED_COORDINATE)

    host = next(node for node in expansion.nodes if node.type is NodeType.HOST)
    assert host.attributes["geo_confidence"] == 0.0
    assert "lat" not in host.attributes


def test_wigle_expander_returns_signals_and_converts_radius_internally() -> None:
    requests: list[httpx.Request] = []
    seed = Node(
        type=NodeType.COORDINATE,
        selector="-27.1,-48.9",
        scope_id=SCOPE,
        attributes={"radius_km": 2, "kind": "wifi"},
    )

    expansion = WigleExpander(_wigle(requests)).expand(seed)

    signal = next(node for node in expansion.nodes if node.type is NodeType.SIGNAL)
    assert signal.selector == "aa:bb:cc:dd:ee:ff"
    assert signal.attributes["ssid"] == "LabNet"
    assert signal.attributes["bssid"] == "aa:bb:cc:dd:ee:ff"
    assert any(edge.pivot is PivotType.GEO_LOCATED for edge in expansion.edges)
    # O port continua centro+raio; a bbox é montada dentro do adapter WiGLE.
    assert "latrange1" in requests[0].url.params


def test_wigle_expander_accepts_a_signal_anchor() -> None:
    seed = Node(
        type=NodeType.SIGNAL,
        selector="aa:bb:cc:dd:ee:ff",
        scope_id=SCOPE,
        attributes={"lat": -27.1, "lon": -48.9, "kind": "wifi"},
    )

    expansion = WigleExpander(_wigle()).expand(seed)

    assert [node.type for node in expansion.nodes].count(NodeType.SIGNAL) == 1


def test_asn_expander_resolves_ip_to_cidr_and_asn() -> None:
    adapter = _ipinfo("ipinfo_ip.json")
    expansion = AsnExpander(adapter).expand(
        Node(type=NodeType.IP, selector="203.0.113.9", scope_id=SCOPE)
    )

    cidr = next(node for node in expansion.nodes if node.type is NodeType.CIDR)
    assert cidr.selector == "203.0.113.0/24"
    assert cidr.attributes["org_name"] == "Example ISP"
    assert {edge.pivot for edge in expansion.edges} == {
        PivotType.CIDR_CONTAINS,
        PivotType.ASN_OWNER,
    }


def test_asn_expander_opens_a_route_from_an_asn_node() -> None:
    asn = Node(
        type=NodeType.ASN,
        selector="AS64500",
        scope_id=SCOPE,
        attributes={"cidr": "203.0.113.0/24", "org_name": "Example ISP"},
    )

    expansion = AsnExpander(_ipinfo("ipinfo_ip.json")).expand(asn)

    cidr = next(node for node in expansion.nodes if node.type is NodeType.CIDR)
    assert cidr.selector == "203.0.113.0/24"
    assert expansion.edges[0].pivot is PivotType.ASN_OWNER


def test_asn_expander_ignores_nodes_outside_its_contract() -> None:
    domain = Node(type=NodeType.DOMAIN, selector="example.com", scope_id=SCOPE)

    assert AsnExpander(_ipinfo("ipinfo_ip.json")).expand(domain).nodes == ()


@pytest.mark.parametrize(
    ("expander", "expected"),
    [
        (lambda: IPInfoExpander(_ipinfo("ipinfo_ip.json"), _ipinfo("ipinfo_ip.json")), "osint.ip.enrich"),
        (lambda: CensysExpander(_censys()), "osint.passive.geo_query"),
        (lambda: ShodanExpander(_shodan()), "osint.passive.geo_query"),
        (lambda: WigleExpander(_wigle()), "osint.passive.signal_query"),
        (lambda: AsnExpander(_ipinfo("ipinfo_ip.json")), "osint.net.resolve"),
    ],
)
def test_every_expander_declares_a_capability(expander, expected: str) -> None:
    assert expander().spec.capability == expected
