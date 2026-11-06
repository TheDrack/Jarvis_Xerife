"""Enrichment loop: fila de prioridade, orçamento e critérios de parada.

O loop é determinístico para os mesmos seeds e expanders:

- prioridade por tipo de nó (``prior``), com desempate pela ordem de descoberta;
- orçamento de expansões (``budget``);
- profundidade máxima de expansão (``max_depth``);
- ``min_confidence`` descarta arestas fracas antes de entrarem no grafo;
- ``coverage_stall_limit`` encerra quando o grafo para de crescer.

O loop não conhece store: persistência fica em ``GraphEnrichmentService``.
"""
from __future__ import annotations

import heapq
import itertools
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.domain.graph.fuse import Fuse
from app.domain.graph.graph import Graph, GraphDelta
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.registry import ExpanderRegistry, RateLimitExceeded
from app.domain.graph.resolver import Resolver

STOP_QUEUE_EMPTY = "queue_empty"
STOP_BUDGET = "budget"
STOP_COVERAGE_STALL = "coverage_stall"
STOP_RATE_LIMITED = "rate_limited"

#: Peso base de prioridade por tipo. Todos os tipos precisam estar presentes
#: para que o comportamento seja previsível.
PRIORITY_BY_TYPE: Mapping[NodeType, float] = MappingProxyType(
    {
        NodeType.CNPJ: 1.00,
        NodeType.PERSON: 0.95,
        NodeType.ORG: 0.95,
        NodeType.EMAIL: 0.90,
        NodeType.USERNAME: 0.85,
        NodeType.DIGITAL_ACCOUNT: 0.80,
        NodeType.DOMAIN: 0.80,
        NodeType.LEAK: 0.80,
        NodeType.DOCUMENT: 0.75,
        NodeType.IP: 0.70,
        NodeType.ASN: 0.65,
        NodeType.CIDR: 0.60,
        NodeType.PHONE: 0.60,
        NodeType.ADDRESS: 0.60,
        NodeType.HOST: 0.55,
        NodeType.LEGAL_CASE: 0.55,
        NodeType.VEHICLE: 0.50,
        NodeType.CPF_HASH: 0.50,
        NodeType.COORDINATE: 0.40,
        NodeType.SIGNAL: 0.30,
        NodeType.SIGNAL_SET: 0.25,
    }
)


@dataclass(frozen=True)
class LoopPolicy:
    """Execution limits for one enrichment run."""

    budget: int = 100
    max_depth: int = 3
    min_confidence: float = 0.0
    coverage_stall_limit: int = 2
    allowed_capabilities: frozenset[str] | None = None
    include_legal_gated: bool = False

    def __post_init__(self) -> None:
        if self.budget < 0:
            raise ValueError("budget must be non-negative")
        if self.max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if self.coverage_stall_limit < 1:
            raise ValueError("coverage_stall_limit must be at least 1")


@dataclass(frozen=True)
class LoopResult:
    """The enriched graph plus what happened during the run."""

    graph: Graph
    expansions: int
    stopped_reason: str
    added_nodes: tuple[str, ...] = ()
    added_edges: tuple[str, ...] = ()
    low_confidence_edges: tuple[str, ...] = ()
    gated_capabilities: tuple[str, ...] = ()
    rate_limited_capabilities: tuple[str, ...] = ()


class EnrichmentLoop:
    """Run expanders breadth-first by priority until a stop criterion hits."""

    def __init__(
        self,
        registry: ExpanderRegistry,
        *,
        resolver: Resolver | None = None,
        fuse: Fuse | None = None,
    ) -> None:
        self._registry = registry
        self._resolver = resolver if resolver is not None else Resolver()
        self._fuse = fuse if fuse is not None else Fuse()

    def prior(self, node: Node) -> float:
        """Deterministic priority of *node*; higher is expanded first."""
        return PRIORITY_BY_TYPE.get(node.type, 0.5)

    def run(
        self,
        seeds: Iterable[Node],
        *,
        graph: Graph | None = None,
        policy: LoopPolicy | None = None,
    ) -> LoopResult:
        rules = policy if policy is not None else LoopPolicy()
        seed_nodes = tuple(seeds)
        current = (graph if graph is not None else Graph()).merge(
            GraphDelta(nodes=seed_nodes)
        )

        heap: list[tuple[float, int, Node, int]] = []
        counter = itertools.count()
        scheduled: set[str] = set()
        for seed in seed_nodes:
            self._schedule(heap, counter, scheduled, seed, 0)

        expansions = 0
        stall = 0
        reason = STOP_QUEUE_EMPTY
        added_nodes: list[str] = []
        added_edges: list[str] = []
        low_confidence: list[str] = []
        gated: set[str] = set()
        rate_limited: set[str] = set()

        while heap:
            if expansions >= rules.budget:
                reason = STOP_BUDGET
                break
            _, _, node, depth = heapq.heappop(heap)
            expanders = self._registry.find_expanders(
                node.type,
                rules.allowed_capabilities,
                include_legal_gated=rules.include_legal_gated,
            )
            if not expanders:
                gated.update(self._registry.gated_capabilities(node.type))
                stall += 1
                if stall >= rules.coverage_stall_limit:
                    reason = STOP_COVERAGE_STALL
                    break
                continue

            produced_new = False
            for expander in expanders:
                if expansions >= rules.budget:
                    reason = STOP_BUDGET
                    break
                try:
                    expansion = expander.expand(node)
                except RateLimitExceeded as exc:
                    rate_limited.add(exc.capability)
                    reason = STOP_RATE_LIMITED
                    break
                expansions += 1
                merged = self._resolver.merge(
                    GraphDelta(nodes=expansion.nodes, edges=expansion.edges)
                )
                weak = tuple(
                    edge
                    for edge in merged.edges
                    if edge.confidence < rules.min_confidence
                )
                low_confidence.extend(edge.id for edge in weak)
                delta = GraphDelta(
                    nodes=merged.nodes,
                    edges=tuple(edge for edge in merged.edges if edge not in weak),
                )
                fused = self._fuse.apply(delta, current)
                known_nodes = current.node_ids
                known_edges = {edge.id for edge in current.edges}
                new_node_ids = tuple(
                    candidate.id
                    for candidate in fused.nodes
                    if candidate.id not in known_nodes
                )
                new_edge_ids = tuple(
                    candidate.id
                    for candidate in fused.edges
                    if candidate.id not in known_edges
                )
                current = current.merge(fused)
                if new_node_ids or new_edge_ids:
                    produced_new = True
                added_nodes.extend(new_node_ids)
                added_edges.extend(new_edge_ids)
                if new_node_ids and depth + 1 < rules.max_depth:
                    for node_id in new_node_ids:
                        child = current.node(node_id)
                        if child is not None:
                            self._schedule(heap, counter, scheduled, child, depth + 1)

            if produced_new:
                stall = 0
            else:
                stall += 1
                if stall >= rules.coverage_stall_limit:
                    reason = STOP_COVERAGE_STALL
                    break
            if reason in {STOP_BUDGET, STOP_RATE_LIMITED}:
                break

        return LoopResult(
            graph=current,
            expansions=expansions,
            stopped_reason=reason,
            added_nodes=tuple(sorted(added_nodes)),
            added_edges=tuple(sorted(added_edges)),
            low_confidence_edges=tuple(sorted(low_confidence)),
            gated_capabilities=tuple(sorted(gated)),
            rate_limited_capabilities=tuple(sorted(rate_limited)),
        )

    @staticmethod
    def _schedule(
        heap: list[tuple[float, int, Node, int]],
        counter: "itertools.count[int]",
        scheduled: set[str],
        node: Node,
        depth: int,
    ) -> None:
        if node.id in scheduled:
            return
        scheduled.add(node.id)
        priority = PRIORITY_BY_TYPE.get(node.type, 0.5)
        heapq.heappush(heap, (-priority, next(counter), node, depth))
