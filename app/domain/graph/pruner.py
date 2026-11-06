"""Retention and pruning for the graph: TTL, confidence, vault and density.

Regras da Fase 1:

- Nós com ``sensitive=True`` saem do grafo e vão para o cofre separado.
- Nós com ``last_seen`` mais antigo que o TTL do seu tipo são removidos.
- Arestas abaixo de ``min_confidence`` são descartadas.
- ``SIGNAL`` denso (mesmo Wi-Fi) agrega em um ``SIGNAL_SET``; os sinais
  individuais deixam o grafo.

Persistir o resultado é responsabilidade da aplicação
(``GraphRetentionService``), não do domínio.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType

from app.domain.graph.edges import Edge
from app.domain.graph.graph import Graph
from app.domain.graph.nodes import Node, NodeType, normalize_selector
from app.domain.graph.sensitive_store import (
    DEFAULT_SENSITIVE_TTL,
    SensitiveStore,
    as_utc,
    utcnow,
)

DEFAULT_TTL_BY_TYPE: Mapping[NodeType, timedelta] = MappingProxyType(
    {
        NodeType.SIGNAL: timedelta(days=2),
        NodeType.SIGNAL_SET: timedelta(days=7),
        NodeType.COORDINATE: timedelta(days=7),
        NodeType.IP: timedelta(days=30),
        NodeType.HOST: timedelta(days=30),
        NodeType.EMAIL: timedelta(days=180),
        NodeType.USERNAME: timedelta(days=180),
        NodeType.DIGITAL_ACCOUNT: timedelta(days=180),
        NodeType.PERSON: timedelta(days=365),
        NodeType.ORG: timedelta(days=365),
        NodeType.LEGAL_CASE: timedelta(days=3650),
    }
)


@dataclass(frozen=True)
class PrunePolicy:
    """Retention parameters. ``default_ttl=None`` means "no global expiry"."""

    ttl_by_type: Mapping[NodeType, timedelta] = field(
        default_factory=lambda: MappingProxyType(dict(DEFAULT_TTL_BY_TYPE))
    )
    default_ttl: timedelta | None = None
    min_confidence: float = 0.0
    density_threshold: int = 50
    sensitive_ttl: timedelta = DEFAULT_SENSITIVE_TTL

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if self.density_threshold < 2:
            raise ValueError("density_threshold must be at least 2")
        if self.sensitive_ttl <= timedelta(0):
            raise ValueError("sensitive_ttl must be positive")
        for ttl in self.ttl_by_type.values():
            if ttl <= timedelta(0):
                raise ValueError("ttl_by_type values must be positive")

    def ttl_for(self, node_type: NodeType) -> timedelta | None:
        return self.ttl_by_type.get(node_type, self.default_ttl)


@dataclass(frozen=True)
class PruneResult:
    """What the pruner removed, moved or aggregated."""

    graph: Graph
    expired: tuple[str, ...] = ()
    moved_to_vault: tuple[str, ...] = ()
    aggregated: tuple[str, ...] = ()
    dropped_edges: tuple[str, ...] = ()
    weak_edges: tuple[str, ...] = ()

    @property
    def removed_node_ids(self) -> tuple[str, ...]:
        return tuple(sorted({*self.expired, *self.moved_to_vault}))


class Pruner:
    """Apply retention to a graph snapshot; persistence stays in application."""

    def __init__(
        self,
        sensitive_store: SensitiveStore,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._sensitive_store = sensitive_store
        self._clock = clock

    def apply(
        self, graph: Graph, policy: PrunePolicy | None = None
    ) -> PruneResult:
        rules = policy if policy is not None else PrunePolicy()
        now = as_utc(self._clock())

        kept: dict[str, Node] = {}
        expired: list[str] = []
        moved: list[str] = []

        for node in graph.nodes:
            if node.requires_sensitive_store:
                self._sensitive_store.put(
                    node, ttl=rules.sensitive_ttl, reason="pruner:retention"
                )
                moved.append(node.id)
                continue
            ttl = rules.ttl_for(node.type)
            if ttl is not None and node.last_seen is not None:
                if now - as_utc(node.last_seen) > ttl:
                    expired.append(node.id)
                    continue
            kept[node.id] = node

        aggregated: list[str] = []
        for signal_set, members in self._density_groups(kept, rules):
            newest = max(
                (member.last_seen for member in members if member.last_seen is not None),
                default=None,
            )
            attributes: dict[str, object] = {
                "kind": members[0].attributes.get("kind", "wifi"),
                "member_count": len(members),
                "member_ids": tuple(sorted(member.id for member in members)),
                "bssid": members[0].attributes.get("bssid"),
                "ssid": members[0].attributes.get("ssid"),
            }
            node = Node(
                type=NodeType.SIGNAL_SET,
                selector=signal_set,
                scope_id=members[0].scope_id,
                last_seen=newest,
                attributes=attributes,
            )
            for member in members:
                kept.pop(member.id, None)
            kept[node.id] = node
            aggregated.append(node.id)

        remaining = set(kept)
        surviving_edges: list[Edge] = []
        dropped: list[str] = []
        weak: list[str] = []
        for edge in graph.edges:
            if edge.src not in remaining or edge.dst not in remaining:
                dropped.append(edge.id)
                continue
            if edge.confidence < rules.min_confidence:
                dropped.append(edge.id)
                weak.append(edge.id)
                continue
            surviving_edges.append(edge)

        pruned = Graph(
            nodes=tuple(sorted(kept.values(), key=lambda node: node.id)),
            edges=tuple(sorted(surviving_edges, key=lambda edge: edge.id)),
        )
        return PruneResult(
            graph=pruned,
            expired=tuple(sorted(expired)),
            moved_to_vault=tuple(sorted(moved)),
            aggregated=tuple(sorted(aggregated)),
            dropped_edges=tuple(sorted(dropped)),
            weak_edges=tuple(sorted(weak)),
        )

    @staticmethod
    def _density_groups(
        kept: dict[str, Node], rules: PrunePolicy
    ) -> list[tuple[str, list[Node]]]:
        groups: dict[tuple[str, str], list[Node]] = defaultdict(list)
        for node in kept.values():
            if node.type is not NodeType.SIGNAL:
                continue
            raw_key = node.attributes.get("bssid") or node.attributes.get("ssid")
            if not isinstance(raw_key, str) or not raw_key.strip():
                continue
            try:
                selector = normalize_selector(NodeType.SIGNAL, raw_key)
            except ValueError:
                continue
            groups[(node.scope_id, selector)].append(node)

        dense: list[tuple[str, list[Node]]] = []
        for (_scope_id, selector), members in groups.items():
            if len(members) >= rules.density_threshold:
                dense.append((selector, sorted(members, key=lambda node: node.id)))
        return dense
