"""Graph expanders for the L1–L3 infrastructure layer (Fase 3).

Cada classe envolve um adapter já existente — nenhuma chamada HTTP nova é
introduzida aqui. O adapter continua sendo o único lugar com rede; o expander
só traduz ``Host``/``Signal``/``GeoLocation`` em ``Node``/``Edge``.

Regras:

- ``IPInfoExpander`` rebaixa ``geo_confidence`` para no máximo 0.3 quando a
  conexão é móvel ou passa por proxy.
- ``Censys`` e ``Shodan`` compartilham a capability ``osint.passive.geo_query``
  e o mesmo contrato de expansão: trocar um pelo outro não muda o pipeline.
- ``WigleExpander`` recebe centro + raio; a conversão para bbox continua dentro
  do adapter WiGLE.
- Todo ``HOST`` produzido por Censys/Shodan carrega ``geo_confidence``.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.application.ports.osint_discovery import (
    GeoProvider,
    NetworkResolver,
    PassiveIntel,
)
from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.expander import Expansion, ExpansionCost, ExpanderSpec
from app.domain.graph.nodes import Node, NodeType, normalize_selector
from app.domain.intelligence.osint import Coordinate, Host, Signal

#: Teto de confiança geográfica para IP móvel ou proxy (regra da Fase 3.1).
GEO_CONFIDENCE_CEILING_MOBILE_OR_PROXY = 0.3


def _bounded_radius(value: Any, *, maximum: float, default: float) -> float:
    try:
        radius = float(value)
    except (TypeError, ValueError):
        return default
    if radius <= 0:
        return default
    return min(radius, maximum)


def _coordinate_from_node(node: Node) -> Coordinate | None:
    lat: Any
    lon: Any
    if node.type is NodeType.COORDINATE:
        try:
            lat_text, lon_text = node.selector.split(",", maxsplit=1)
            lat, lon = float(lat_text), float(lon_text)
        except (TypeError, ValueError):
            return None
        raw_accuracy: Any = node.attributes.get("accuracy_m", 1000.0)
    else:
        lat, lon = node.attributes.get("lat"), node.attributes.get("lon")
        if (
            not isinstance(lat, (int, float))
            or isinstance(lat, bool)
            or not isinstance(lon, (int, float))
            or isinstance(lon, bool)
        ):
            return None
        raw_accuracy = node.attributes.get("accuracy_m", 1000.0)
    try:
        return Coordinate(
            lat=float(lat),
            lon=float(lon),
            accuracy_m=float(raw_accuracy),
            source=str(node.attributes.get("source", "graph")),
        )
    except (TypeError, ValueError):
        return None


def _cidrs_from_node(node: Node, *, default_cidr: str | None = None) -> tuple[str, ...]:
    if node.type is NodeType.CIDR:
        return (node.selector,)
    raw = node.attributes.get("cidrs")
    if isinstance(raw, (list, tuple)) and raw:
        return tuple(str(value) for value in raw)
    single = node.attributes.get("cidr")
    if isinstance(single, str) and single.strip():
        return (single.strip(),)
    return (default_cidr,) if default_cidr else ()


def _coordinate_node(
    coordinate: Coordinate,
    *,
    scope_id: str,
    source: str,
    geo_confidence: float | None = None,
) -> Node:
    attributes: dict[str, Any] = {
        "accuracy_m": coordinate.accuracy_m,
        "source": source,
    }
    if geo_confidence is not None:
        attributes["geo_confidence"] = geo_confidence
    return Node(
        type=NodeType.COORDINATE,
        selector=f"{coordinate.lat},{coordinate.lon}",
        scope_id=scope_id,
        attributes=attributes,
    )


def _dedupe_nodes(nodes: Sequence[Node]) -> tuple[Node, ...]:
    unique: dict[str, Node] = {}
    for node in nodes:
        unique.setdefault(node.id, node)
    return tuple(unique.values())


def _dedupe_edges(edges: Sequence[Edge]) -> tuple[Edge, ...]:
    unique: dict[str, Edge] = {}
    for edge in edges:
        unique.setdefault(edge.id, edge)
    return tuple(unique.values())


def _host_expansion(
    hosts: Sequence[Host], *, scope_id: str, source: str
) -> Expansion:
    nodes: list[Node] = []
    edges: list[Edge] = []
    for host in hosts:
        attributes: dict[str, Any] = {
            "geo_confidence": host.geo_confidence,
            "ports": list(host.ports),
            "sources": list(host.sources),
        }
        for key in ("country", "org", "asn", "hostnames", "autonomous_system"):
            value = host.metadata.get(key)
            if value is not None:
                attributes[key] = value
        if host.geo is not None:
            attributes.update(
                {
                    "lat": host.geo.lat,
                    "lon": host.geo.lon,
                    "accuracy_m": host.geo.accuracy_m,
                }
            )
        host_node = Node(
            type=NodeType.HOST,
            selector=host.ip,
            scope_id=scope_id,
            attributes=attributes,
        )
        nodes.append(host_node)
        if host.geo is not None:
            coordinate = _coordinate_node(
                host.geo,
                scope_id=scope_id,
                source=source,
                geo_confidence=host.geo_confidence,
            )
            nodes.append(coordinate)
            edges.append(
                Edge.derive(
                    host_node,
                    coordinate,
                    PivotType.GEO_LOCATED,
                    selector_used=coordinate.selector,
                    source=source,
                )
            )
    return Expansion(
        nodes=_dedupe_nodes(nodes),
        edges=_dedupe_edges(edges),
    )


class IPInfoExpander:
    """IP → coordinate + ASN (ORG is derived by the Resolver)."""

    SPEC = ExpanderSpec(
        name="ipinfo",
        accepts=frozenset({NodeType.IP}),
        produces=frozenset(
            {NodeType.COORDINATE, NodeType.ASN, NodeType.ORG}
        ),
        capability="osint.ip.enrich",
        cost=ExpansionCost.ZERO,
    )

    def __init__(self, geo: GeoProvider, resolver: NetworkResolver) -> None:
        self._geo = geo
        self._resolver = resolver

    @property
    def spec(self) -> ExpanderSpec:
        return self.SPEC

    def expand(self, node: Node) -> Expansion:
        if node.type is not NodeType.IP:
            return Expansion()

        location = self._geo.locate(node.selector)
        confidence = location.geo_confidence
        if location.connection_type == "mobile" or location.is_proxy:
            confidence = min(confidence, GEO_CONFIDENCE_CEILING_MOBILE_OR_PROXY)

        nodes: list[Node] = []
        edges: list[Edge] = []

        if location.coordinate is not None:
            coordinate = _coordinate_node(
                location.coordinate,
                scope_id=node.scope_id,
                source="ipinfo",
                geo_confidence=confidence,
            )
            coordinate_attributes = {
                **dict(coordinate.attributes),
                "connection_type": location.connection_type,
                "is_proxy": location.is_proxy,
            }
            coordinate = coordinate.model_copy(
                update={"attributes": coordinate_attributes}
            )
            nodes.append(coordinate)
            edges.append(
                Edge.derive(
                    node,
                    coordinate,
                    PivotType.GEO_LOCATED,
                    selector_used=coordinate.selector,
                    source="ipinfo",
                )
            )

        network = self._resolver.resolve(node.selector)
        if network.asn is not None:
            asn = Node(
                type=NodeType.ASN,
                selector=f"AS{network.asn}",
                scope_id=node.scope_id,
                attributes={
                    "org_name": network.org,
                    "country": network.country,
                    "cidr": network.cidr,
                    "source": "ipinfo",
                },
            )
            nodes.append(asn)
            edges.append(
                Edge.derive(
                    asn,
                    node,
                    PivotType.ASN_OWNER,
                    selector_used=asn.selector,
                    source="ipinfo",
                )
            )

        return Expansion(nodes=_dedupe_nodes(nodes), edges=_dedupe_edges(edges))


class _HostSearchExpander:
    """Shared contract for Censys and Shodan (same capability, same output)."""

    SPEC: ExpanderSpec
    SOURCE: str = ""

    def __init__(self, intel: PassiveIntel, *, limit: int = 100) -> None:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        self._intel = intel
        self._limit = limit

    @property
    def spec(self) -> ExpanderSpec:
        return self.SPEC

    def expand(self, node: Node) -> Expansion:
        coordinate = _coordinate_from_node(node)
        if coordinate is None:
            return Expansion()
        default_cidr = (
            f"{node.selector}/32" if node.type is NodeType.IP else None
        )
        cidrs = _cidrs_from_node(node, default_cidr=default_cidr)
        if not cidrs:
            return Expansion()
        radius = _bounded_radius(
            node.attributes.get("radius_km"), maximum=500.0, default=5.0
        )
        hosts = self._intel.query_radius(
            coordinate, radius, {"cidrs": list(cidrs), "limit": self._limit}
        )
        return _host_expansion(
            tuple(host for host in hosts if isinstance(host, Host)),
            scope_id=node.scope_id,
            source=self.SOURCE,
        )


class CensysExpander(_HostSearchExpander):
    """Coordinate/CIDR → HOST via Censys."""

    SOURCE = "censys"
    SPEC = ExpanderSpec(
        name="censys",
        accepts=frozenset({NodeType.COORDINATE, NodeType.CIDR}),
        produces=frozenset({NodeType.HOST}),
        capability="osint.passive.geo_query",
        cost=ExpansionCost.LOW,
    )


class ShodanExpander(_HostSearchExpander):
    """Coordinate/IP → HOST via Shodan, with the same contract as Censys."""

    SOURCE = "shodan"
    SPEC = ExpanderSpec(
        name="shodan",
        accepts=frozenset({NodeType.COORDINATE, NodeType.IP}),
        produces=frozenset({NodeType.HOST}),
        capability="osint.passive.geo_query",
        cost=ExpansionCost.LOW,
    )


class WigleExpander:
    """Coordinate/SIGNAL → SIGNAL via WiGLE (center + radius contract)."""

    SPEC = ExpanderSpec(
        name="wigle",
        accepts=frozenset({NodeType.COORDINATE, NodeType.SIGNAL}),
        produces=frozenset({NodeType.SIGNAL}),
        capability="osint.passive.signal_query",
        cost=ExpansionCost.LOW,
    )

    def __init__(self, intel: PassiveIntel, *, limit: int = 100) -> None:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        self._intel = intel
        self._limit = limit

    @property
    def spec(self) -> ExpanderSpec:
        return self.SPEC

    def expand(self, node: Node) -> Expansion:
        coordinate = _coordinate_from_node(node)
        if coordinate is None:
            return Expansion()
        radius = _bounded_radius(
            node.attributes.get("radius_km"), maximum=100.0, default=1.0
        )
        kind = node.attributes.get("kind", "wifi")
        if kind not in {"wifi", "bluetooth", "all"}:
            kind = "wifi"
        signals = self._intel.query_radius(
            coordinate, radius, {"kind": kind, "limit": self._limit}
        )

        nodes: list[Node] = []
        edges: list[Edge] = []
        for signal in signals:
            if not isinstance(signal, Signal):
                continue
            attributes: dict[str, Any] = {
                "kind": signal.kind,
                "source": signal.source,
                "ssid": signal.metadata.get("ssid") or signal.metadata.get("name"),
                "encryption": signal.metadata.get("encryption"),
            }
            if signal.kind == "wifi":
                attributes["bssid"] = normalize_selector(
                    NodeType.SIGNAL, signal.identifier
                )
            if signal.geo is not None:
                attributes.update(
                    {
                        "lat": signal.geo.lat,
                        "lon": signal.geo.lon,
                        "accuracy_m": signal.geo.accuracy_m,
                    }
                )
            signal_node = Node(
                type=NodeType.SIGNAL,
                selector=signal.identifier,
                scope_id=node.scope_id,
                attributes=attributes,
            )
            nodes.append(signal_node)
            if signal.geo is not None:
                signal_coordinate = _coordinate_node(
                    signal.geo,
                    scope_id=node.scope_id,
                    source=signal.source,
                )
                nodes.append(signal_coordinate)
                edges.append(
                    Edge.derive(
                        signal_node,
                        signal_coordinate,
                        PivotType.GEO_LOCATED,
                        selector_used=signal_coordinate.selector,
                        source="wigle",
                    )
                )

        return Expansion(nodes=_dedupe_nodes(nodes), edges=_dedupe_edges(edges))


class AsnExpander:
    """IP/ASN/ORG → CIDR (+ ASN) using the network resolver."""

    SPEC = ExpanderSpec(
        name="asn",
        accepts=frozenset({NodeType.IP, NodeType.ASN, NodeType.ORG}),
        produces=frozenset({NodeType.CIDR, NodeType.ORG}),
        capability="osint.net.resolve",
        cost=ExpansionCost.LOW,
    )

    def __init__(self, resolver: NetworkResolver) -> None:
        self._resolver = resolver

    @property
    def spec(self) -> ExpanderSpec:
        return self.SPEC

    def expand(self, node: Node) -> Expansion:
        if node.type is NodeType.IP:
            return self._from_ip(node)
        if node.type is NodeType.ASN:
            return self._from_asn(node)
        if node.type is NodeType.ORG:
            return self._from_org(node)
        return Expansion()

    def _from_ip(self, node: Node) -> Expansion:
        network = self._resolver.resolve(node.selector)
        nodes: list[Node] = [
            Node(
                type=NodeType.CIDR,
                selector=network.cidr,
                scope_id=node.scope_id,
                attributes={
                    "asn": network.asn,
                    "org_name": network.org,
                    "country": network.country,
                    "source": "ipinfo",
                },
            )
        ]
        edges: list[Edge] = [
            Edge.derive(
                nodes[0],
                node,
                PivotType.CIDR_CONTAINS,
                selector_used=network.cidr,
                source="ipinfo",
            )
        ]
        if network.asn is not None:
            asn = Node(
                type=NodeType.ASN,
                selector=f"AS{network.asn}",
                scope_id=node.scope_id,
                attributes={
                    "org_name": network.org,
                    "country": network.country,
                    "cidr": network.cidr,
                    "source": "ipinfo",
                },
            )
            nodes.append(asn)
            edges.append(
                Edge.derive(
                    asn,
                    node,
                    PivotType.ASN_OWNER,
                    selector_used=asn.selector,
                    source="ipinfo",
                )
            )
        return Expansion(nodes=_dedupe_nodes(nodes), edges=_dedupe_edges(edges))

    def _from_asn(self, node: Node) -> Expansion:
        cidr = node.attributes.get("cidr") or node.attributes.get("route")
        if not isinstance(cidr, str) or not cidr.strip():
            return Expansion()
        cidr_node = Node(
            type=NodeType.CIDR,
            selector=cidr,
            scope_id=node.scope_id,
            attributes={"asn": node.selector, "source": "graph"},
        )
        return Expansion(
            nodes=(cidr_node,),
            edges=(
                Edge.derive(
                    node,
                    cidr_node,
                    PivotType.ASN_OWNER,
                    selector_used=cidr_node.selector,
                    source="asn",
                ),
            ),
        )

    def _from_org(self, node: Node) -> Expansion:
        asn_value = node.attributes.get("asn")
        if isinstance(asn_value, bool) or not isinstance(asn_value, (int, str)):
            return Expansion()
        text = str(asn_value).strip()
        if not text:
            return Expansion()
        selector = text if text.lower().startswith("as") else f"AS{text}"
        asn_node = Node(
            type=NodeType.ASN,
            selector=selector,
            scope_id=node.scope_id,
            attributes={
                "org_name": node.selector,
                "cidr": node.attributes.get("cidr"),
                "source": "graph",
            },
        )
        return Expansion(
            nodes=(asn_node,),
            edges=(
                Edge.derive(
                    asn_node,
                    node,
                    PivotType.ASN_OWNER,
                    selector_used=asn_node.selector,
                    source="asn",
                ),
            ),
        )
