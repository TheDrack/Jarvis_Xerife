from __future__ import annotations

from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.fuse import Fuse, haversine_km
from app.domain.graph.graph import Graph, GraphDelta
from app.domain.graph.nodes import Node, NodeType

SCOPE = "case-1"


def _ip(scope: str = SCOPE) -> Node:
    return Node(type=NodeType.IP, selector="203.0.113.9", scope_id=scope)


def _host(**attributes: object) -> Node:
    return Node(
        type=NodeType.HOST,
        selector="host.example",
        scope_id=SCOPE,
        attributes=attributes,
    )


def _dns(src: Node, dst: Node, selector: str = "host.example") -> Edge:
    return Edge.derive(
        src, dst, PivotType.DNS_A, selector_used=selector, source="test"
    )


def test_novel_when_the_graph_is_empty() -> None:
    src, dst = _ip(), _host()
    edge = _dns(src, dst)

    fused = Fuse().apply(GraphDelta(nodes=(src, dst), edges=(edge,)), Graph())

    assert fused.nodes[0].interest == "novel"
    assert fused.edges[0].interest == "novel"


def test_confirmed_when_the_same_evidence_already_exists() -> None:
    src, dst = _ip(), _host()
    edge = _dns(src, dst)
    graph = Graph(nodes=(src, dst), edges=(edge,))

    fused = Fuse().apply(GraphDelta(edges=(edge,)), graph)

    assert fused.edges[0].interest == "confirmed"


def test_confirmed_when_another_pivot_corroborates() -> None:
    src, dst = _ip(), _host()
    existing = _dns(src, dst)
    corroborating = Edge.derive(
        src,
        dst,
        PivotType.WHOIS_REGISTRANT,
        selector_used="acme",
        source="whois",
    )
    graph = Graph(nodes=(src, dst), edges=(existing,))

    fused = Fuse().apply(GraphDelta(edges=(corroborating,)), graph)

    assert fused.edges[0].interest == "confirmed"


def test_discrepancy_when_the_same_pivot_uses_a_different_selector() -> None:
    src, dst = _ip(), _host()
    existing = _dns(src, dst, "host.example")
    conflicting = _dns(src, dst, "other.example")
    graph = Graph(nodes=(src, dst), edges=(existing,))

    fused = Fuse().apply(GraphDelta(edges=(conflicting,)), graph)

    assert fused.edges[0].interest == "discrepancy"


def test_geo_discrepancy_when_coordinates_are_far_apart() -> None:
    existing = _host(lat=-27.1, lon=-48.9)
    incoming = _host(lat=-23.55, lon=-46.63)
    graph = Graph(nodes=(existing,))

    fused = Fuse().apply(GraphDelta(nodes=(incoming,)), graph)

    assert fused.nodes[0].interest == "discrepancy"
    assert haversine_km((-27.1, -48.9), (-23.55, -46.63)) > 50


def test_geo_confirmed_when_coordinates_are_close() -> None:
    existing = _host(lat=-27.1, lon=-48.9)
    incoming = _host(lat=-27.11, lon=-48.91)
    graph = Graph(nodes=(existing,))

    fused = Fuse().apply(GraphDelta(nodes=(incoming,)), graph)

    assert fused.nodes[0].interest == "confirmed"


def test_a_second_location_for_the_same_host_is_a_discrepancy() -> None:
    host = _host()
    first = Node(
        type=NodeType.COORDINATE, selector="-27.1,-48.9", scope_id=SCOPE
    )
    second = Node(
        type=NodeType.COORDINATE, selector="-23.55,-46.63", scope_id=SCOPE
    )
    edge_first = Edge.derive(
        host, first, PivotType.GEO_LOCATED, selector_used=first.selector, source="a"
    )
    edge_second = Edge.derive(
        host, second, PivotType.GEO_LOCATED, selector_used=second.selector, source="b"
    )
    graph = Graph(nodes=(host, first), edges=(edge_first,))

    fused = Fuse().apply(GraphDelta(edges=(edge_second,)), graph)

    assert fused.edges[0].interest == "discrepancy"


def test_attribute_conflict_marks_the_node_as_discrepancy() -> None:
    existing = _host(asn=64500)
    incoming = _host(asn=64501)
    graph = Graph(nodes=(existing,))

    fused = Fuse().apply(GraphDelta(nodes=(incoming,)), graph)

    assert fused.nodes[0].interest == "discrepancy"


def test_fuse_does_not_mutate_inputs() -> None:
    src, dst = _ip(), _host()
    edge = _dns(src, dst)
    graph = Graph(nodes=(src, dst), edges=(edge,))

    Fuse().apply(GraphDelta(nodes=(src, dst), edges=(edge,)), graph)

    assert edge.interest is None
    assert graph.edges[0].interest is None
