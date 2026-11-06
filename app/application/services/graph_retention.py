"""Orquestração da retenção: aplica ``Pruner`` e persiste o resultado.

O domínio decide o que sai; esta camada decide como gravar no ``GraphStorePort``.
"""
from __future__ import annotations

from app.application.ports.graph_store import GraphStorePort
from app.domain.graph.graph import GraphDelta
from app.domain.graph.pruner import PrunePolicy, Pruner, PruneResult


class GraphRetentionService:
    """Apply retention to one scope and persist deletions and aggregations."""

    def __init__(self, store: GraphStorePort, pruner: Pruner) -> None:
        self._store = store
        self._pruner = pruner

    def prune_scope(
        self, scope_id: str, policy: PrunePolicy | None = None
    ) -> PruneResult:
        before = self._store.load(scope_id)
        result = self._pruner.apply(before, policy)

        before_node_ids = {node.id for node in before.nodes}
        after_node_ids = {node.id for node in result.graph.nodes}
        removed_nodes = sorted(before_node_ids - after_node_ids)

        before_edge_ids = {edge.id for edge in before.edges}
        after_edge_ids = {edge.id for edge in result.graph.edges}
        removed_edges = sorted(before_edge_ids - after_edge_ids)

        new_nodes = tuple(
            node for node in result.graph.nodes if node.id not in before_node_ids
        )
        new_edges = tuple(
            edge for edge in result.graph.edges if edge.id not in before_edge_ids
        )

        if removed_edges:
            self._store.delete_edges(removed_edges)
        if removed_nodes:
            self._store.delete_nodes(removed_nodes)
        if new_nodes:
            self._store.upsert_delta(GraphDelta(nodes=new_nodes))
        if new_edges:
            self._store.upsert_delta(GraphDelta(edges=new_edges))
        return result
