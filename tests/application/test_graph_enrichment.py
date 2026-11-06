from __future__ import annotations

import pytest

from app.adapters.infrastructure.graph.store import SQLiteGraphStore
from app.application.services.graph_enrichment import GraphEnrichmentService
from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.expander import Expansion, ExpansionCost, ExpanderSpec
from app.domain.graph.loop import EnrichmentLoop
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import ScopeViolation
from app.domain.graph.registry import ExpanderRegistry

SCOPE = "case-1"
SEED = Node(type=NodeType.IP, selector="203.0.113.9", scope_id=SCOPE)


class FakeExpander:
    def __init__(self, spec: ExpanderSpec, result: Expansion) -> None:
        self.spec = spec
        self._result = result

    def expand(self, node: Node) -> Expansion:
        return self._result


def _registry() -> ExpanderRegistry:
    ip_expander = FakeExpander(
        ExpanderSpec(
            name="fake.ip",
            accepts=frozenset({NodeType.IP}),
            produces=frozenset({NodeType.HOST, NodeType.ASN, NodeType.COORDINATE}),
            capability="osint.ip.enrich",
            cost=ExpansionCost.LOW,
        ),
        Expansion(
            nodes=(
                Node(
                    type=NodeType.HOST,
                    selector="host1.example",
                    scope_id=SCOPE,
                    attributes={"lat": -27.1, "lon": -48.9},
                ),
                Node(
                    type=NodeType.ASN,
                    selector="AS64500",
                    scope_id=SCOPE,
                    attributes={"org_name": "Example ISP"},
                ),
                Node(
                    type=NodeType.COORDINATE,
                    selector="-27.1,-48.9",
                    scope_id=SCOPE,
                ),
            ),
            edges=(
                Edge.derive(
                    SEED,
                    Node(
                        type=NodeType.HOST,
                        selector="host1.example",
                        scope_id=SCOPE,
                    ),
                    PivotType.DNS_A,
                    selector_used="host1.example",
                    source="fake.ip",
                ),
            ),
        ),
    )
    registry = ExpanderRegistry()
    registry.register(ip_expander)
    return registry


def test_enrich_scope_persists_evidence_and_is_idempotent(tmp_path) -> None:
    store = SQLiteGraphStore(tmp_path / "graph.sqlite")
    service = GraphEnrichmentService(store, EnrichmentLoop(_registry()))

    first = service.enrich_scope(SCOPE, [SEED])

    types = {node.type for node in store.nodes(SCOPE)}
    assert {
        NodeType.IP,
        NodeType.HOST,
        NodeType.ASN,
        NodeType.COORDINATE,
        NodeType.ORG,
    } <= types
    assert first.added_nodes

    exported = store.export_scope(SCOPE)
    second = service.enrich_scope(SCOPE, [SEED])

    assert second.added_nodes == ()
    assert second.added_edges == ()
    assert store.export_scope(SCOPE) == exported
    store.close()


def test_enrich_scope_rejects_a_seed_from_another_scope(tmp_path) -> None:
    store = SQLiteGraphStore(tmp_path / "graph.sqlite")
    service = GraphEnrichmentService(store, EnrichmentLoop(_registry()))
    foreign = Node(type=NodeType.IP, selector="198.51.100.7", scope_id="case-2")

    with pytest.raises(ScopeViolation):
        service.enrich_scope(SCOPE, [foreign])

    assert store.nodes() == ()
    store.close()
