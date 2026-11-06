from __future__ import annotations

import pytest

from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.policy import (
    MIN_PEPPER_BYTES,
    ScopePolicy,
    ScopeViolation,
    SensitiveDataError,
    SensitivityPolicy,
)

VALID_CPF = "529.982.247-25"
PEPPER = b"phase0-test-pepper-0123456789"


def _policy() -> SensitivityPolicy:
    return SensitivityPolicy(pepper=PEPPER)


def _email(scope_id: str = "case-1") -> Node:
    return Node(type=NodeType.EMAIL, selector="owner@acme.example", scope_id=scope_id)


def test_cpf_is_hashed_never_stored() -> None:
    selector = _policy().hash_cpf(VALID_CPF)

    assert selector.startswith("sha256:")
    assert len(selector) == 71
    assert "52998224725" not in selector
    assert selector == _policy().hash_cpf("52998224725")


def test_cpf_hash_depends_on_the_pepper() -> None:
    other = SensitivityPolicy(pepper=b"another-pepper-0123456789")
    assert _policy().hash_cpf(VALID_CPF) != other.hash_cpf(VALID_CPF)


def test_invalid_cpf_is_refused_instead_of_hashed() -> None:
    with pytest.raises(SensitiveDataError):
        _policy().hash_cpf("529.982.247-26")
    with pytest.raises(SensitiveDataError):
        _policy().hash_cpf("123")


def test_short_pepper_is_refused() -> None:
    with pytest.raises(SensitiveDataError):
        SensitivityPolicy(pepper=b"short")
    assert MIN_PEPPER_BYTES == 16


def test_cpf_node_lives_in_the_sensitive_store_only() -> None:
    node = _policy().cpf_node(VALID_CPF, scope_id="case-1")

    assert node.type is NodeType.CPF_HASH
    assert node.sensitive is True
    assert node.requires_sensitive_store is True
    assert node.attributes == {}


def test_assert_graph_safe_rejects_plaintext_cpf_payloads() -> None:
    policy = _policy()
    contaminated = Node(
        type=NodeType.HOST,
        selector="example.com",
        scope_id="case-1",
        attributes={"note": f"cpf {VALID_CPF}"},
    )

    policy.assert_graph_safe(_email())
    with pytest.raises(SensitiveDataError):
        policy.assert_graph_safe(contaminated)


def test_person_node_cannot_be_keyed_by_a_cpf_digest() -> None:
    policy = _policy()
    digest = policy.hash_cpf(VALID_CPF)
    miskeyed = Node(type=NodeType.PERSON, selector=digest, scope_id="case-1")

    with pytest.raises(SensitiveDataError):
        policy.assert_graph_safe(miskeyed)


def test_scope_policy_authorizes_only_its_own_scope() -> None:
    policy = ScopePolicy(scope_id="case-1")
    node = _email()

    assert policy.allows(node) is True
    assert policy.require(node) is node
    assert policy.allows(_email("case-2")) is False
    with pytest.raises(ScopeViolation):
        policy.require(_email("case-2"))


def test_scope_policy_gates_sensitive_pivots() -> None:
    cpf = _policy().cpf_node(VALID_CPF, scope_id="case-1")

    with pytest.raises(ScopeViolation):
        ScopePolicy(scope_id="case-1").require(cpf)

    authorized = ScopePolicy(scope_id="case-1", allow_sensitive_pivots=True)
    assert authorized.require(cpf) is cpf


def test_scope_policy_requires_a_scope() -> None:
    with pytest.raises(ScopeViolation):
        ScopePolicy(scope_id="  ")
