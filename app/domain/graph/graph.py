"""Graph snapshot and delta values shared by Resolver, Pruner and the store.

``Graph`` é imutável e íntegro: toda aresta aponta para um nó presente, sem ids
duplicados. ``GraphDelta`` é um lote parcial (o que um adapter devolve ou o que o
``Resolver`` deriva) e pode referenciar nós fora do lote.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.domain.graph.edges import Edge
from app.domain.graph.nodes import Node, NodeType


class GraphIntegrityError(ValueError):
    """Raised when a graph is structurally inconsistent."""


@dataclass(frozen=True)
class GraphDelta:
    """A batch of nodes and edges, deduplicated only when merged."""

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    duplicates: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "duplicates", tuple(self.duplicates))

    @property
    def is_empty(self) -> bool:
        return not self.nodes and not self.edges


@dataclass(frozen=True)
class Graph:
    """An immutable, scope-consistent snapshot of the knowledge graph."""

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise GraphIntegrityError("graph contains duplicate node ids")
        edge_ids = {edge.id for edge in self.edges}
        if len(edge_ids) != len(self.edges):
            raise GraphIntegrityError("graph contains duplicate edge ids")
        for edge in self.edges:
            if edge.src not in node_ids or edge.dst not in node_ids:
                raise GraphIntegrityError(
                    f"edge {edge.id} references a node outside the graph"
                )

    def __len__(self) -> int:
        return len(self.nodes)

    @property
    def node_ids(self) -> frozenset[str]:
        return frozenset(node.id for node in self.nodes)

    def node(self, node_id: str) -> Node | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def nodes_of(self, *types: NodeType) -> tuple[Node, ...]:
        wanted = frozenset(types)
        return tuple(node for node in self.nodes if node.type in wanted)

    def edges_of(self, node_id: str) -> tuple[Edge, ...]:
        return tuple(
            edge for edge in self.edges if node_id in (edge.src, edge.dst)
        )

    def edges_between(self, src_id: str, dst_id: str) -> tuple[Edge, ...]:
        return tuple(
            edge
            for edge in self.edges
            if {edge.src, edge.dst} == {src_id, dst_id}
        )

    def subgraph(self, scope_id: str) -> "Graph":
        """Nodes of one scope and edges whose endpoints are both inside it."""
        nodes = tuple(node for node in self.nodes if node.scope_id == scope_id)
        ids = {node.id for node in nodes}
        edges = tuple(
            edge
            for edge in self.edges
            if edge.scope_id == scope_id and edge.src in ids and edge.dst in ids
        )
        return Graph(nodes=nodes, edges=edges)

    def merge(self, delta: GraphDelta) -> "Graph":
        """Return a new graph with *delta* applied, deduplicated by id."""
        nodes = {node.id: node for node in self.nodes}
        for node in delta.nodes:
            nodes.setdefault(node.id, node)
        edges = {edge.id: edge for edge in self.edges}
        for edge in delta.edges:
            edges.setdefault(edge.id, edge)
        return Graph(
            nodes=tuple(sorted(nodes.values(), key=lambda node: node.id)),
            edges=tuple(sorted(edges.values(), key=lambda edge: edge.id)),
        )

    def to_payload(self, *, scope_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "nodes": [
                node.model_dump(mode="json")
                for node in sorted(self.nodes, key=lambda node: node.id)
            ],
            "edges": [
                edge.model_dump(mode="json")
                for edge in sorted(self.edges, key=lambda edge: edge.id)
            ],
        }
        if scope_id is not None:
            payload = {"scope_id": scope_id, **payload}
        return payload

    def to_json(self, *, scope_id: str | None = None) -> str:
        """Deterministic JSON export, suitable for the globe/Osiris consumers."""
        return json.dumps(
            self.to_payload(scope_id=scope_id), ensure_ascii=False, sort_keys=True
        )
