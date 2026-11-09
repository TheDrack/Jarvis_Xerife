from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from app.adapters.infrastructure.graph.store import SQLiteGraphStore
from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.graph import GraphDelta, GraphIntegrityError
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import SensitiveDataError, SensitivityPolicy

SCOPE = "case-1"


@pytest.fixture()
def store(tmp_path) -> SQLiteGraphStore:
    instance = SQLiteGraphStore(tmp_path / "graph.sqlite")
    yield instance
    instance.close()


def _ip(selector: str = "203.0.113.9", scope: str = SCOPE) -> Node:
    return Node(type=NodeType.IP, selector=selector, scope_id=scope)


def _asn(scope: str = SCOPE) -> Node:
    return Node(type=NodeType.ASN, selector="AS64500", scope_id=scope)


def _link(src: Node, dst: Node) -> Edge:
    return Edge.derive(
        src, dst, PivotType.ASN_OWNER, selector_used="as64500", source="test"
    )


def test_upserting_the_same_node_twice_does_not_duplicate(store) -> None:
    node = _ip()

    first = store.upsert_nodes([node])
    second = store.upsert_nodes([node])

    assert (first.inserted, first.duplicates) == (1, 0)
    assert (second.inserted, second.duplicates) == (0, 1)
    assert len(store.nodes()) == 1
    assert store.get_node(node.id) is not None


def test_required_indexes_exist(tmp_path) -> None:
    path = tmp_path / "graph.sqlite"
    SQLiteGraphStore(path).close()

    with sqlite3.connect(path) as connection:
        node_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('nodes')")
        }
        edge_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('edges')")
        }
        node_columns = {
            row[2]
            for row in connection.execute(
                "PRAGMA index_info('idx_nodes_type_selector_scope')"
            )
        }

    assert {"idx_nodes_type_selector_scope", "idx_nodes_scope"} <= node_indexes
    assert {
        "idx_edges_src",
        "idx_edges_dst",
        "idx_edges_pivot",
        "idx_edges_scope",
    } <= edge_indexes
    assert node_columns == {"type", "selector", "scope_id"}


def test_sensitive_nodes_are_refused_by_the_main_store(store) -> None:
    cpf = SensitivityPolicy(pepper=b"phase1-test-pepper-0123456789").cpf_node(
        "529.982.247-25", scope_id=SCOPE
    )

    with pytest.raises(SensitiveDataError):
        store.upsert_nodes([cpf])

    assert store.nodes() == ()


def test_edges_require_both_endpoints(store) -> None:
    src, dst = _ip(), _asn()

    with pytest.raises(GraphIntegrityError):
        store.upsert_edges([_link(src, dst)])


def test_scope_isolation_and_json_export(store) -> None:
    src, dst = _ip(), _asn()
    other = _ip("198.51.100.7", "case-2")
    store.upsert_delta(
        GraphDelta(nodes=(src, dst, other), edges=(_link(src, dst),))
    )

    scope = store.load(SCOPE)
    payload = json.loads(store.export_scope(SCOPE))

    assert scope.node_ids == {src.id, dst.id}
    assert payload["scope_id"] == SCOPE
    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1
    assert store.export_scope(SCOPE) == store.export_scope(SCOPE)


def test_deleting_a_node_cascades_to_its_edges(store) -> None:
    src, dst = _ip(), _asn()
    store.upsert_delta(GraphDelta(nodes=(src, dst), edges=(_link(src, dst),)))

    removed = store.delete_nodes([src.id])

    assert removed == 1
    assert store.edges() == ()
    assert store.get_node(dst.id) is not None


def test_find_nodes_by_type_and_scope(store) -> None:
    src, dst = _ip(), _asn()
    other_scope = _ip("198.51.100.7", "case-2")
    store.upsert_nodes([src, dst, other_scope])

    assert [node.id for node in store.find_nodes(NodeType.IP)] == [
        sorted([src.id, other_scope.id])[0],
        sorted([src.id, other_scope.id])[1],
    ]
    assert [node.id for node in store.find_nodes(NodeType.IP, SCOPE)] == [src.id]


def test_roundtrip_preserves_last_seen_and_attributes(store) -> None:
    observed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    node = Node(
        type=NodeType.IP,
        selector="203.0.113.9",
        scope_id=SCOPE,
        last_seen=observed,
        attributes={"asn": 64500, "country": "BR"},
    )
    store.upsert_nodes([node])

    loaded = store.get_node(node.id)

    assert loaded is not None
    assert loaded.last_seen == observed
    assert dict(loaded.attributes) == {"asn": 64500, "country": "BR"}


def test_get_edge_by_id_is_scoped(store) -> None:
    src, dst = _ip(), _asn()
    link = _link(src, dst)
    store.upsert_delta(GraphDelta(nodes=(src, dst), edges=(link,)))

    assert store.get_edge(link.id) == link
    assert store.get_edge(link.id, scope_id=SCOPE) == link
    assert store.get_edge(link.id, scope_id="case-2") is None
    assert store.get_edge("sha256:" + "0" * 64) is None
