from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.graph.confidence import (
    CROSS_SCOPE_FACTOR,
    PIVOT_FACTOR,
    STRONG_PIVOTS,
    edge_confidence,
    is_strong_pivot,
)
from app.domain.graph.edges import WEAK_PIVOT_CAP, Edge, PivotType, edge_id
from app.domain.graph.nodes import Node, NodeType


def _nodes(scope_a: str = "case-1", scope_b: str = "case-1") -> tuple[Node, Node]:
    return (
        Node(type=NodeType.EMAIL, selector="owner@acme.example", scope_id=scope_a),
        Node(type=NodeType.CNPJ, selector="11.222.333/0001-81", scope_id=scope_b),
    )


def test_pivot_factor_covers_every_pivot() -> None:
    assert set(PIVOT_FACTOR) == set(PivotType)


def test_pivot_factors_are_probabilities() -> None:
    assert all(0.0 < factor <= 1.0 for factor in PIVOT_FACTOR.values())


def test_brazilian_pivot_factors_match_the_plan() -> None:
    assert PIVOT_FACTOR[PivotType.CNPJ_OWNER] == 0.95
    assert PIVOT_FACTOR[PivotType.ADDRESS_SHARED] == 0.5
    assert PIVOT_FACTOR[PivotType.VEHICLE_OWNER] == 0.4


def test_strong_pivots_are_the_three_identity_anchors() -> None:
    assert STRONG_PIVOTS == {
        PivotType.COMMIT_EMAIL,
        PivotType.WHOIS_REGISTRANT,
        PivotType.CNPJ_OWNER,
    }
    assert is_strong_pivot(PivotType.COMMIT_EMAIL) is True
    assert is_strong_pivot(PivotType.SAME_HANDLE) is False


def test_edge_confidence_is_deterministic_and_scope_aware() -> None:
    email, cnpj = _nodes()
    same_scope = edge_confidence(email, cnpj, PivotType.CNPJ_OWNER)
    cross_scope = edge_confidence(*_nodes("case-1", "case-2"), PivotType.CNPJ_OWNER)

    assert same_scope == 0.95
    assert cross_scope == round(0.95 * CROSS_SCOPE_FACTOR, 4)


def test_edge_id_is_derived_and_stable() -> None:
    assert edge_id("a", "b", PivotType.SAME_HANDLE, "handle", "sherlock") == edge_id(
        "a", "b", PivotType.SAME_HANDLE, "handle", "sherlock"
    )
    assert edge_id("a", "b", PivotType.SAME_HANDLE, "handle", "sherlock") != edge_id(
        "a", "b", PivotType.SAME_HANDLE, "handle", "other-source"
    )


def test_derive_takes_confidence_from_the_pivot_table() -> None:
    email, cnpj = _nodes()
    edge = Edge.derive(
        email,
        cnpj,
        PivotType.CNPJ_OWNER,
        selector_used="11222333000181",
        source="cnpjaberto",
    )

    assert edge.confidence == 0.95
    assert edge.scope_id == "case-1"
    assert edge.src == email.id
    assert edge.dst == cnpj.id
    assert edge.id.startswith("sha256:")


def test_edge_is_immutable_and_rejects_a_forged_id() -> None:
    src, dst = _nodes()
    edge = Edge(
        src=src.id,
        dst=dst.id,
        pivot=PivotType.SAME_HANDLE,
        selector_used="john",
        source="sherlock",
        confidence=0.6,
        scope_id="case-1",
    )

    with pytest.raises(ValidationError):
        edge.confidence = 0.9
    with pytest.raises(ValidationError):
        Edge(
            id="sha256:" + "f" * 64,
            src=src.id,
            dst=dst.id,
            pivot=PivotType.SAME_HANDLE,
            selector_used="john",
            source="sherlock",
            confidence=0.6,
            scope_id="case-1",
        )


def test_edge_rejects_self_links_and_blank_evidence() -> None:
    src, _ = _nodes()

    for kwargs in (
        {"src": src.id, "dst": src.id},
        {"src": src.id, "dst": src.id.replace("a", "b"), "selector_used": "   "},
        {"src": src.id, "dst": src.id.replace("a", "b"), "source": ""},
    ):
        payload = {
            "src": src.id,
            "dst": "sha256:" + "b" * 64,
            "pivot": PivotType.SAME_HANDLE,
            "selector_used": "john",
            "source": "sherlock",
            "confidence": 0.6,
            "scope_id": "case-1",
        }
        payload.update(kwargs)
        with pytest.raises(ValidationError):
            Edge(**payload)


def test_vehicle_owner_is_weak_and_capped() -> None:
    plaque = Node(type=NodeType.VEHICLE, selector="ABC1234", scope_id="case-1")
    owner = Node(type=NodeType.PERSON, selector="Fulano", scope_id="case-1")

    derived = Edge.derive(
        plaque, owner, PivotType.VEHICLE_OWNER, selector_used="ABC1234", source="apify"
    )
    forced = Edge(
        src=plaque.id,
        dst=owner.id,
        pivot=PivotType.VEHICLE_OWNER,
        selector_used="ABC1234",
        source="apify",
        confidence=0.99,
        scope_id="case-1",
    )

    assert derived.pivot_weak is True
    assert forced.confidence == WEAK_PIVOT_CAP
    assert forced.pivot_weak is True
