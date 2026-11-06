from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.graph import Graph
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import SensitivityPolicy
from app.domain.graph.pruner import PrunePolicy, Pruner
from app.domain.graph.sensitive_store import InMemorySensitiveStore

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
SCOPE = "case-1"
PEPPER = b"phase1-test-pepper-0123456789"


def _pruner(vault: InMemorySensitiveStore | None = None) -> Pruner:
    store = vault if vault is not None else InMemorySensitiveStore(clock=lambda: NOW)
    return Pruner(store, clock=lambda: NOW)


def _signals(count: int, bssid: str = "AA:BB:CC:DD:EE:FF") -> list[Node]:
    return [
        Node(
            type=NodeType.SIGNAL,
            selector=f"02:00:{index // 65536:02x}:{(index // 256) % 256:02x}:{index % 256:02x}:01",
            scope_id=SCOPE,
            attributes={"kind": "wifi", "bssid": bssid, "ssid": "MinhaRede"},
        )
        for index in range(count)
    ]


def test_expired_nodes_are_removed_by_type_ttl() -> None:
    old = Node(
        type=NodeType.IP,
        selector="203.0.113.9",
        scope_id=SCOPE,
        last_seen=NOW - timedelta(days=2),
    )
    fresh = Node(
        type=NodeType.IP,
        selector="203.0.113.10",
        scope_id=SCOPE,
        last_seen=NOW,
    )
    policy = PrunePolicy(ttl_by_type={NodeType.IP: timedelta(days=1)})

    result = _pruner().apply(Graph(nodes=(old, fresh)), policy)

    assert result.expired == (old.id,)
    assert result.graph.node_ids == frozenset({fresh.id})


def test_nodes_without_timestamp_are_not_expired() -> None:
    node = Node(type=NodeType.IP, selector="203.0.113.9", scope_id=SCOPE)
    policy = PrunePolicy(ttl_by_type={NodeType.IP: timedelta(days=1)})

    result = _pruner().apply(Graph(nodes=(node,)), policy)

    assert result.graph.node_ids == frozenset({node.id})


def test_sensitive_nodes_move_to_the_vault() -> None:
    vault = InMemorySensitiveStore(clock=lambda: NOW)
    cpf = SensitivityPolicy(pepper=PEPPER).cpf_node(
        "529.982.247-25", scope_id=SCOPE
    )

    result = _pruner(vault).apply(Graph(nodes=(cpf,)))

    assert result.moved_to_vault == (cpf.id,)
    assert result.graph.node_ids == frozenset()
    assert vault.contains(cpf.id)
    assert [record.action for record in vault.access_log()] == ["put"]


def test_edges_below_min_confidence_are_dropped() -> None:
    email = Node(type=NodeType.EMAIL, selector="john@acme.example", scope_id=SCOPE)
    cnpj = Node(type=NodeType.CNPJ, selector="11.222.333/0001-81", scope_id=SCOPE)
    weak = Edge.derive(
        email, cnpj, PivotType.ADDRESS_SHARED, selector_used="acme", source="test"
    )
    strong = Edge.derive(
        email, cnpj, PivotType.CNPJ_OWNER, selector_used="11222333000181", source="test"
    )
    policy = PrunePolicy(min_confidence=0.6)

    result = _pruner().apply(
        Graph(nodes=(email, cnpj), edges=(weak, strong)), policy
    )

    assert result.weak_edges == (weak.id,)
    assert [edge.id for edge in result.graph.edges] == [strong.id]


def test_five_hundred_signals_aggregate_into_one_signal_set() -> None:
    signals = _signals(500)

    result = _pruner().apply(Graph(nodes=tuple(signals)), PrunePolicy())

    assert len(result.aggregated) == 1
    remaining = result.graph.nodes
    assert len(remaining) == 1
    signal_set = remaining[0]
    assert signal_set.type is NodeType.SIGNAL_SET
    assert signal_set.selector == "aa:bb:cc:dd:ee:ff"
    assert signal_set.attributes["member_count"] == 500


def test_sparse_signals_are_not_aggregated() -> None:
    signals = _signals(3)

    result = _pruner().apply(Graph(nodes=tuple(signals)), PrunePolicy())

    assert result.aggregated == ()
    assert result.graph.node_ids == frozenset(signal.id for signal in signals)


def test_signals_without_wifi_key_are_kept() -> None:
    signal = Node(type=NodeType.SIGNAL, selector="my-network", scope_id=SCOPE)

    result = _pruner().apply(Graph(nodes=(signal,)), PrunePolicy(density_threshold=2))

    assert result.graph.node_ids == frozenset({signal.id})
