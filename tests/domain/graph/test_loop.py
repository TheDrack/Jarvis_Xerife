from __future__ import annotations

from collections.abc import Callable

import pytest

from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.expander import Expansion, ExpansionCost, ExpanderSpec
from app.domain.graph.loop import (
    PRIORITY_BY_TYPE,
    STOP_BUDGET,
    STOP_COVERAGE_STALL,
    STOP_RATE_LIMITED,
    EnrichmentLoop,
    LoopPolicy,
)
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.registry import ExpanderRegistry, RateLimit
from app.domain.graph.resolver import AdapterBoundaryError

SCOPE = "case-1"
SEED = Node(type=NodeType.IP, selector="203.0.113.9", scope_id=SCOPE)


class FakeExpander:
    def __init__(
        self,
        spec: ExpanderSpec,
        result: Expansion | Callable[[Node], Expansion],
    ) -> None:
        self.spec = spec
        self._result = result
        self.calls = 0

    def expand(self, node: Node) -> Expansion:
        self.calls += 1
        return self._result(node) if callable(self._result) else self._result


def _spec(
    name: str,
    accepts: set[NodeType],
    produces: set[NodeType],
    capability: str,
) -> ExpanderSpec:
    return ExpanderSpec(
        name=name,
        accepts=frozenset(accepts),
        produces=frozenset(produces),
        capability=capability,
        cost=ExpansionCost.LOW,
    )


def _ip_expander() -> FakeExpander:
    spec = _spec(
        "fake.ip",
        {NodeType.IP},
        {NodeType.HOST, NodeType.COORDINATE, NodeType.ASN},
        "osint.ip.enrich",
    )

    def expand(node: Node) -> Expansion:
        host = Node(
            type=NodeType.HOST,
            selector="host1.example",
            scope_id=node.scope_id,
            attributes={"lat": -27.1, "lon": -48.9},
        )
        coordinate = Node(
            type=NodeType.COORDINATE,
            selector="-27.1,-48.9",
            scope_id=node.scope_id,
        )
        asn = Node(
            type=NodeType.ASN,
            selector="AS64500",
            scope_id=node.scope_id,
            attributes={"org_name": "Example ISP"},
        )
        return Expansion(
            nodes=(host, coordinate, asn),
            edges=(
                Edge.derive(
                    node, host, PivotType.DNS_A, selector_used="host1.example",
                    source="fake.ip",
                ),
                Edge.derive(
                    node, coordinate, PivotType.GEO_LOCATED,
                    selector_used=coordinate.selector, source="fake.ip",
                ),
                Edge.derive(
                    node, asn, PivotType.ASN_OWNER, selector_used="as64500",
                    source="fake.ip",
                ),
            ),
        )

    return FakeExpander(spec, expand)


def _host_expander() -> FakeExpander:
    spec = _spec(
        "fake.host",
        {NodeType.HOST},
        {NodeType.DOMAIN},
        "osint.net.resolve",
    )

    def expand(node: Node) -> Expansion:
        domain = Node(
            type=NodeType.DOMAIN, selector="example.com", scope_id=node.scope_id
        )
        return Expansion(
            nodes=(domain,),
            edges=(
                Edge.derive(
                    node, domain, PivotType.DNS_A,
                    selector_used="example.com", source="fake.host",
                ),
            ),
        )

    return FakeExpander(spec, expand)


def _registry(*expanders: FakeExpander) -> ExpanderRegistry:
    registry = ExpanderRegistry()
    for expander in expanders:
        registry.register(expander)
    return registry


def test_a_single_seed_grows_at_least_three_node_types() -> None:
    loop = EnrichmentLoop(_registry(_ip_expander(), _host_expander()))

    result = loop.run([SEED])

    types = {node.type for node in result.graph.nodes}
    assert {
        NodeType.IP,
        NodeType.HOST,
        NodeType.COORDINATE,
        NodeType.ASN,
        NodeType.DOMAIN,
    } <= types
    assert result.expansions == 2


def test_running_the_loop_twice_does_not_duplicate_anything() -> None:
    loop = EnrichmentLoop(_registry(_ip_expander(), _host_expander()))

    first = loop.run([SEED])
    second = loop.run([SEED], graph=first.graph)

    assert second.added_nodes == ()
    assert second.added_edges == ()
    assert second.graph == first.graph


def test_budget_stops_the_run() -> None:
    loop = EnrichmentLoop(_registry(_ip_expander(), _host_expander()))

    result = loop.run([SEED], policy=LoopPolicy(budget=1))

    assert result.expansions == 1
    assert result.stopped_reason == STOP_BUDGET


def test_max_depth_limits_expansion() -> None:
    loop = EnrichmentLoop(_registry(_ip_expander(), _host_expander()))

    result = loop.run([SEED], policy=LoopPolicy(max_depth=1))

    types = {node.type for node in result.graph.nodes}
    assert NodeType.DOMAIN not in types
    assert NodeType.HOST in types


def test_coverage_stall_stops_when_nothing_new_appears() -> None:
    empty = FakeExpander(
        _spec("fake.empty", {NodeType.IP}, set(), "osint.empty"),
        lambda node: Expansion(),
    )
    loop = EnrichmentLoop(_registry(empty))

    result = loop.run([SEED], policy=LoopPolicy(coverage_stall_limit=1))

    assert result.expansions == 1
    assert result.stopped_reason == STOP_COVERAGE_STALL
    assert result.added_nodes == ()


def test_an_inactive_expander_is_reported_as_gated() -> None:
    spec = _spec("fake.signal", {NodeType.IP}, {NodeType.SIGNAL}, "osint.signal.capture")
    gated = FakeExpander(
        ExpanderSpec(
            name=spec.name,
            accepts=spec.accepts,
            produces=spec.produces,
            capability=spec.capability,
            active=False,
        ),
        lambda node: Expansion(),
    )
    loop = EnrichmentLoop(_registry(gated))

    result = loop.run([SEED])

    assert result.expansions == 0
    assert result.gated_capabilities == ("osint.signal.capture",)


def test_legal_gated_expander_requires_explicit_opt_in() -> None:
    gated = FakeExpander(
        ExpanderSpec(
            name="fake.vehicle",
            accepts=frozenset({NodeType.IP}),
            produces=frozenset({NodeType.VEHICLE}),
            capability="osint.br.vehicle.lookup",
            legal_gated=True,
        ),
        lambda node: Expansion(),
    )
    loop = EnrichmentLoop(_registry(gated))

    blocked = loop.run([SEED])
    allowed = loop.run(
        [SEED], policy=LoopPolicy(include_legal_gated=True)
    )

    assert blocked.expansions == 0
    assert blocked.gated_capabilities == ("osint.br.vehicle.lookup",)
    assert allowed.expansions == 1


def test_weak_edges_are_dropped_before_entering_the_graph() -> None:
    def expand(node: Node) -> Expansion:
        host = Node(
            type=NodeType.HOST, selector="host.example", scope_id=node.scope_id
        )
        return Expansion(
            nodes=(host,),
            edges=(
                Edge.derive(
                    node, host, PivotType.GEO_PROXIMITY,
                    selector_used="near", source="fake.proximity",
                ),
            ),
        )

    expander = FakeExpander(
        _spec("fake.proximity", {NodeType.IP}, {NodeType.HOST}, "osint.proximity"),
        expand,
    )
    loop = EnrichmentLoop(_registry(expander))

    result = loop.run([SEED], policy=LoopPolicy(min_confidence=0.5))

    assert len(result.low_confidence_edges) == 1
    assert result.graph.edges == ()
    assert len(result.graph.nodes) == 2


def test_expander_cannot_create_derived_nodes() -> None:
    person = Node(type=NodeType.PERSON, selector="john", scope_id=SCOPE)
    expander = FakeExpander(
        _spec("fake.person", {NodeType.IP}, {NodeType.PERSON}, "osint.identity"),
        Expansion(nodes=(person,)),
    )
    loop = EnrichmentLoop(_registry(expander))

    with pytest.raises(AdapterBoundaryError):
        loop.run([SEED])


def test_priority_is_higher_for_identity_than_signals() -> None:
    loop = EnrichmentLoop(ExpanderRegistry())
    cnpj = Node(type=NodeType.CNPJ, selector="11222333000181", scope_id=SCOPE)
    signal = Node(
        type=NodeType.SIGNAL, selector="aa:bb:cc:dd:ee:ff", scope_id=SCOPE
    )

    assert loop.prior(cnpj) > loop.prior(signal)


def test_priority_table_covers_every_node_type() -> None:
    assert set(PRIORITY_BY_TYPE) == set(NodeType)


def test_rate_limit_stops_the_run_and_reports_the_capability() -> None:
    now = [0.0]
    registry = ExpanderRegistry(clock=lambda: now[0])
    registry.register(_ip_expander())
    registry.set_rate_limit(
        "osint.ip.enrich", RateLimit(max_calls=1, period_seconds=60)
    )
    second_seed = Node(
        type=NodeType.IP, selector="203.0.113.10", scope_id=SCOPE
    )

    result = EnrichmentLoop(registry).run([SEED, second_seed])

    assert result.expansions == 1
    assert result.stopped_reason == STOP_RATE_LIMITED
    assert result.rate_limited_capabilities == ("osint.ip.enrich",)
