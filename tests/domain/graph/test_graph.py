from __future__ import annotations

import json

import pytest

from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.graph import Graph, GraphDelta, GraphIntegrityError
from app.domain.graph.nodes import Node, NodeType


def _ip(selector: str = "203.0.113.9", scope: str = "case-1") -> Node:
    return Node(type=NodeType.IP, selector=selector, scope_id=scope)


def _asn(scope: str = "case-1") -> Node:
    return Node(type=NodeType.ASN, selector="AS64500", scope_id=scope)


def _link(src: Node, dst: Node) -> Edge:
    return Edge.derive(
        src, dst, PivotType.ASN_OWNER, selector_used="as64500", source="test"
    )


def test_graph_rejects_edge_with_missing_node() -> None:
    src, dst = _ip(), _asn()

    with pytest.raises(GraphIntegrityError):
        Graph(nodes=(src,), edges=(_link(src, dst),))


def test_graph_rejects_duplicate_nodes() -> None:
    node = _ip()

    with pytest.raises(GraphIntegrityError):
        Graph(nodes=(node, node))


def test_subgraph_keeps_only_its_scope() -> None:
    a1, a2 = _ip(), _asn()
    b1 = _ip("198.51.100.7", "case-2")
    graph = Graph(nodes=(a1, a2, b1), edges=(_link(a1, a2),))

    subgraph = graph.subgraph("case-1")

    assert subgraph.node_ids == {a1.id, a2.id}
    assert len(subgraph.edges) == 1
    assert graph.subgraph("case-2").node_ids == {b1.id}


def test_merge_is_idempotent() -> None:
    a1, a2 = _ip(), _asn()
    graph = Graph(nodes=(a1,), edges=())

    merged = graph.merge(GraphDelta(nodes=(a1, a2), edges=(_link(a1, a2),)))
    again = merged.merge(GraphDelta(nodes=(a1, a2), edges=(_link(a1, a2),)))

    assert merged == again
    assert len(merged.nodes) == 2


def test_json_export_is_deterministic_and_self_describing() -> None:
    a1, a2 = _ip(), _asn()
    graph = Graph(nodes=(a2, a1), edges=(_link(a1, a2),))

    payload = json.loads(graph.to_json(scope_id="case-1"))

    assert payload["scope_id"] == "case-1"
    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1
    assert payload["edges"][0]["pivot"] == "asn_owner"
    assert graph.to_json(scope_id="case-1") == graph.to_json(scope_id="case-1")
