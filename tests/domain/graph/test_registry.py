from __future__ import annotations

import pytest

from app.domain.graph.expander import Expansion, ExpansionCost, ExpanderSpec
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.registry import (
    ExpanderRegistry,
    RateLimit,
    RateLimitExceeded,
)


class _Expander:
    def __init__(self, spec: ExpanderSpec) -> None:
        self.spec = spec

    def expand(self, node: Node) -> Expansion:
        return Expansion()


def _spec(
    name: str = "fake.ip",
    accepts: tuple[NodeType, ...] = (NodeType.IP,),
    capability: str = "osint.ip.enrich",
    *,
    active: bool = True,
    legal_gated: bool = False,
) -> ExpanderSpec:
    return ExpanderSpec(
        name=name,
        accepts=frozenset(accepts),
        produces=frozenset({NodeType.HOST}),
        capability=capability,
        cost=ExpansionCost.LOW,
        active=active,
        legal_gated=legal_gated,
    )


def test_spec_requires_name_accepts_and_valid_cost() -> None:
    with pytest.raises(ValueError):
        ExpanderSpec(
            name=" ",
            accepts=frozenset({NodeType.IP}),
            produces=frozenset(),
            capability="osint.ip.enrich",
        )
    with pytest.raises(ValueError):
        ExpanderSpec(
            name="fake",
            accepts=frozenset(),
            produces=frozenset(),
            capability="osint.ip.enrich",
        )
    with pytest.raises(ValueError):
        ExpanderSpec(
            name="fake",
            accepts=frozenset({NodeType.IP}),
            produces=frozenset(),
            capability="osint.ip.enrich",
            cost="low",  # type: ignore[arg-type]
        )


def test_duplicate_expander_names_are_rejected() -> None:
    registry = ExpanderRegistry()
    registry.register(_Expander(_spec()))

    with pytest.raises(ValueError):
        registry.register(_Expander(_spec()))


def test_find_expanders_filters_by_type_capability_and_gate() -> None:
    registry = ExpanderRegistry()
    registry.register(_Expander(_spec("ip", capability="osint.ip.enrich")))
    registry.register(_Expander(_spec("censys", capability="osint.passive.geo_query")))
    registry.register(_Expander(_spec("off", capability="osint.off", active=False)))
    registry.register(
        _Expander(_spec("legal", capability="osint.scan", legal_gated=True))
    )

    assert [expander.spec.name for expander in registry.find_expanders(NodeType.IP)] == [
        "censys",
        "ip",
    ]
    assert [
        expander.spec.name
        for expander in registry.find_expanders(
            NodeType.IP, ["osint.passive.geo_query"]
        )
    ] == ["censys"]
    assert registry.find_expanders(NodeType.SIGNAL) == ()
    assert [
        expander.spec.name
        for expander in registry.find_expanders(
            NodeType.IP, include_legal_gated=True
        )
    ] == ["censys", "ip", "legal"]


def test_find_gap_separates_missing_from_gated() -> None:
    registry = ExpanderRegistry()
    registry.register(_Expander(_spec("ip", capability="osint.ip.enrich")))
    registry.register(
        _Expander(_spec("signal", capability="osint.signal.capture", active=False))
    )

    gap = registry.find_gap(
        required_capabilities=("osint.ip.enrich", "osint.missing.cap"),
        optional_capabilities=("osint.signal.capture",),
    )

    assert gap.available == ("osint.ip.enrich",)
    assert gap.gated == ("osint.signal.capture",)
    assert gap.missing == ("osint.missing.cap",)
    assert gap.ready is False


def test_gated_is_not_a_failure() -> None:
    registry = ExpanderRegistry()
    registry.register(
        _Expander(_spec("signal", capability="osint.signal.capture", active=False))
    )

    gap = registry.find_gap(required_capabilities=("osint.signal.capture",))

    assert gap.missing == ()
    assert gap.gated == ("osint.signal.capture",)
    assert gap.ready is True


def test_gap_is_scoped_by_node_type() -> None:
    registry = ExpanderRegistry()
    registry.register(_Expander(_spec("ip", accepts=(NodeType.IP,))))

    assert registry.find_gap(node_type=NodeType.IP).available == ("osint.ip.enrich",)
    assert registry.find_gap(node_type=NodeType.SIGNAL).available == ()


def test_gap_report_is_serialisable_for_agents() -> None:
    report = ExpanderRegistry().find_gap(required_capabilities=("osint.ip.enrich",))

    assert report.as_dict() == {
        "available": [],
        "missing": ["osint.ip.enrich"],
        "gated": [],
    }


def test_rate_limit_is_per_capability_and_rolls_with_the_clock() -> None:
    now = [0.0]
    registry = ExpanderRegistry(clock=lambda: now[0])
    registry.register(_Expander(_spec("ip", capability="osint.ip.enrich")))
    registry.register(_Expander(_spec("censys", capability="osint.passive.geo_query")))
    registry.set_rate_limit(
        "osint.ip.enrich", RateLimit(max_calls=2, period_seconds=60)
    )
    node = Node(type=NodeType.IP, selector="203.0.113.9", scope_id="case-1")

    limited = registry.find_expanders(NodeType.IP, ["osint.ip.enrich"])[0]
    limited.expand(node)
    limited.expand(node)
    with pytest.raises(RateLimitExceeded):
        limited.expand(node)

    # Outra capability não foi afetada pela janela esgotada.
    other = registry.find_expanders(NodeType.IP, ["osint.passive.geo_query"])[0]
    other.expand(node)

    now[0] = 61.0
    limited.expand(node)
