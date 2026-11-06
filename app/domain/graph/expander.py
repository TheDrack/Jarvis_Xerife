"""Expander contract: adapters viram funções puras de expansão (Fase 2).

``ExpanderSpec`` é a ficha declarativa que o ``ExpanderRegistry`` usa para
descobrir quem aceita um tipo de nó e para reportar lacunas. ``produces``
descreve o efeito observável: ``PERSON``/``ORG`` só aparecem no grafo via
``Resolver.derive_*``; o loop recusa qualquer nó derivado devolvido por um
expander.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from app.domain.graph.edges import Edge
from app.domain.graph.nodes import Node, NodeType


class ExpansionCost(str, Enum):
    """Custo relativo declarado, para orçamento e priorização do loop."""

    ZERO = "zero"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Expansion:
    """Nodes and edges produced by one expander for one input node."""

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))


@dataclass(frozen=True)
class ExpanderSpec:
    """Declarative identity of an expander."""

    name: str
    accepts: frozenset[NodeType]
    produces: frozenset[NodeType]
    capability: str
    cost: ExpansionCost = ExpansionCost.ZERO
    active: bool = True
    legal_gated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("expander name must be a non-empty string")
        if not isinstance(self.capability, str) or not self.capability.strip():
            raise ValueError("capability must be a non-empty string")
        if not self.accepts:
            raise ValueError("accepts must contain at least one node type")
        if not isinstance(self.cost, ExpansionCost):
            raise ValueError("cost must be an ExpansionCost")


@runtime_checkable
class Expander(Protocol):
    """Pure expansion function: no network outside its own port."""

    @property
    def spec(self) -> ExpanderSpec: ...

    def expand(self, node: Node) -> Expansion: ...
