from __future__ import annotations

from app.adapters.infrastructure.graph.store import SQLiteGraphStore
from app.application.services.graph_retention import GraphRetentionService
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.pruner import PrunePolicy, Pruner
from app.domain.graph.sensitive_store import InMemorySensitiveStore

SCOPE = "case-1"


def _signals(count: int) -> list[Node]:
    return [
        Node(
            type=NodeType.SIGNAL,
            selector=f"02:00:{index // 65536:02x}:{(index // 256) % 256:02x}:{index % 256:02x}:01",
            scope_id=SCOPE,
            attributes={"kind": "wifi", "bssid": "AA:BB:CC:DD:EE:FF", "ssid": "Rede"},
        )
        for index in range(count)
    ]


def test_prune_scope_persists_the_signal_aggregation(tmp_path) -> None:
    store = SQLiteGraphStore(tmp_path / "graph.sqlite")
    store.upsert_nodes(_signals(3))
    service = GraphRetentionService(store, Pruner(InMemorySensitiveStore()))

    result = service.prune_scope(
        SCOPE, PrunePolicy(ttl_by_type={}, density_threshold=2)
    )

    remaining = store.nodes(SCOPE)
    assert len(result.aggregated) == 1
    assert len(remaining) == 1
    assert remaining[0].type is NodeType.SIGNAL_SET
    assert store.load(SCOPE).node_ids == {remaining[0].id}
    store.close()
