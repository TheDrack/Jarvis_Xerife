"""Persistence port for the OSINT graph (implemented by infrastructure adapters).

O domínio depende só deste contrato: ``Resolver`` e ``Pruner`` nunca importam
SQLite. ``GraphStorePort`` recusa nós sensíveis: eles pertencem ao cofre.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.domain.graph.edges import Edge
from app.domain.graph.graph import Graph, GraphDelta
from app.domain.graph.nodes import Node, NodeType


@dataclass(frozen=True)
class UpsertReport:
    """Outcome of one upsert batch: idempotency is observable."""

    inserted: int = 0
    duplicates: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.duplicates


@runtime_checkable
class GraphStorePort(Protocol):
    def upsert_nodes(self, nodes: Iterable[Node]) -> UpsertReport: ...

    def upsert_edges(self, edges: Iterable[Edge]) -> UpsertReport: ...

    def upsert_delta(self, delta: GraphDelta) -> tuple[UpsertReport, UpsertReport]: ...

    def get_node(self, node_id: str) -> Node | None: ...

    def nodes(self, scope_id: str | None = None) -> tuple[Node, ...]: ...

    def edges(self, scope_id: str | None = None) -> tuple[Edge, ...]: ...

    def load(self, scope_id: str) -> Graph: ...

    def find_nodes(
        self, node_type: NodeType, scope_id: str | None = None
    ) -> tuple[Node, ...]: ...

    def delete_nodes(self, node_ids: Iterable[str]) -> int: ...

    def delete_edges(self, edge_ids: Iterable[str]) -> int: ...

    def export_scope(self, scope_id: str, *, format: str = "json") -> str: ...

    def close(self) -> None: ...
