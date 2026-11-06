"""Orquestração do enriquecimento: roda o loop e persiste o grafo resultante.

O domínio decide expansão, fusão e derivação; esta camada aplica escopo,
carrega o grafo do store, executa o loop, deriva ``PERSON``/``ORG`` e grava
somente o que é novo.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from app.application.ports.graph_store import GraphStorePort
from app.domain.graph.graph import GraphDelta
from app.domain.graph.loop import EnrichmentLoop, LoopPolicy, LoopResult
from app.domain.graph.nodes import Node
from app.domain.graph.policy import ScopePolicy
from app.domain.graph.resolver import Resolver


class GraphEnrichmentService:
    """Enrich one scope from explicit seeds and persist the new evidence."""

    def __init__(
        self,
        store: GraphStorePort,
        loop: EnrichmentLoop,
        *,
        resolver: Resolver | None = None,
    ) -> None:
        self._store = store
        self._loop = loop
        self._resolver = resolver if resolver is not None else Resolver()

    def enrich_scope(
        self,
        scope_id: str,
        seeds: Sequence[Node],
        policy: LoopPolicy | None = None,
    ) -> LoopResult:
        scope = ScopePolicy(scope_id=scope_id)
        seed_nodes = tuple(scope.require(seed) for seed in seeds)

        before = self._store.load(scope_id)
        result = self._loop.run(seed_nodes, graph=before, policy=policy)

        derived = self._resolver.derive_person_org(result.graph)
        final = result.graph.merge(derived)

        before_node_ids = before.node_ids
        before_edge_ids = {edge.id for edge in before.edges}
        new_nodes = tuple(
            node for node in final.nodes if node.id not in before_node_ids
        )
        new_edges = tuple(
            edge for edge in final.edges if edge.id not in before_edge_ids
        )

        if new_nodes:
            self._store.upsert_delta(GraphDelta(nodes=new_nodes))
        if new_edges:
            self._store.upsert_delta(GraphDelta(edges=new_edges))

        return replace(
            result,
            graph=final,
            added_nodes=tuple(sorted(node.id for node in new_nodes)),
            added_edges=tuple(sorted(edge.id for edge in new_edges)),
        )
