from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.graph.nodes import (
    NORMALIZERS,
    Node,
    NodeType,
    node_id,
    normalize_selector,
)

VALID_CPF = "529.982.247-25"
VALID_CNPJ = "11.222.333/0001-81"
HASH = "sha256:" + "a" * 64

#: Um seletor válido por tipo. Também prova que NORMALIZERS cobre o enum.
SAMPLES: dict[NodeType, str] = {
    NodeType.IP: "203.0.113.9",
    NodeType.CIDR: "203.0.113.9/24",
    NodeType.ASN: "AS64500",
    NodeType.DOMAIN: "Example.COM.",
    NodeType.EMAIL: "User@Example.com",
    NodeType.USERNAME: "@JohnDoe",
    NodeType.PERSON: "Ana Maria",
    NodeType.ORG: "Acme Ltda.",
    NodeType.DOCUMENT: "C:\\Docs\\a.pdf",
    NodeType.SIGNAL: "AA-BB-CC-DD-EE-FF",
    NodeType.SIGNAL_SET: "aa:bb:cc:dd:ee:ff",
    NodeType.COORDINATE: "-27.1,-48.9",
    NodeType.HOST: "example.com",
    NodeType.LEAK: "Collection#1",
    NodeType.CNPJ: VALID_CNPJ,
    NodeType.CPF_HASH: HASH,
    NodeType.ADDRESS: "80.000-000",
    NodeType.PHONE: "(11) 99999-8888",
    NodeType.VEHICLE: "abc-1234",
    NodeType.LEGAL_CASE: "0001234-56.2023.8.26.0100",
    NodeType.DIGITAL_ACCOUNT: "GitHub:JohnDoe",
}


def test_every_node_type_has_a_normalizer_and_a_sample() -> None:
    assert set(NORMALIZERS) == set(NodeType)
    assert set(SAMPLES) == set(NodeType)


def test_cpf_does_not_exist_as_a_node_type() -> None:
    values = {node_type.value for node_type in NodeType}
    assert "cpf" not in values
    assert "cpf_hash" in values


@pytest.mark.parametrize(
    ("node_type", "raw", "expected"),
    [
        (NodeType.EMAIL, "  John.Doe@Example.COM ", "john.doe@example.com"),
        (NodeType.EMAIL, "user@BÜCHER.de", "user@xn--bcher-kva.de"),
        (NodeType.CNPJ, " 11.222.333/0001-81 ", "11222333000181"),
        (NodeType.DOMAIN, "BÜCHER.DE.", "xn--bcher-kva.de"),
        (NodeType.IP, "2001:0DB8:0:0:0:0:0:1", "2001:db8::1"),
        (NodeType.CIDR, "203.0.113.9/24", "203.0.113.0/24"),
        (NodeType.ASN, " AS64500 ", "as64500"),
        (NodeType.ASN, "64500", "as64500"),
        (NodeType.COORDINATE, "-27.1, -48.9", "-27.100000,-48.900000"),
        (NodeType.USERNAME, "@JohnDoe", "johndoe"),
        (NodeType.SIGNAL, "AA-BB-CC-DD-EE-FF", "aa:bb:cc:dd:ee:ff"),
        (NodeType.SIGNAL, "aabbccddeeff", "aa:bb:cc:dd:ee:ff"),
        (NodeType.SIGNAL, "MinhaRede Wi-Fi", "minharede wi-fi"),
        (NodeType.HOST, "Example.COM.", "example.com"),
        (NodeType.HOST, "203.0.113.9", "203.0.113.9"),
        (NodeType.PHONE, "(11) 99999-8888", "11999998888"),
        (NodeType.PHONE, "+55 11 99999-8888", "+5511999998888"),
        (NodeType.VEHICLE, "abc-1234", "ABC1234"),
        (NodeType.ADDRESS, "80.000-000", "80000-000"),
        (NodeType.ADDRESS, "Av.  Brasil,  100", "av. brasil, 100"),
        (NodeType.DOCUMENT, "C:\\Docs\\Relatório.PDF", "c:/docs/relatório.pdf"),
        (NodeType.PERSON, "  Ana   Maria  Silva ", "ana maria silva"),
        (NodeType.ORG, "ACME  Ltda.", "acme ltda."),
        (NodeType.LEAK, "Collection#1", "collection#1"),
        (NodeType.DIGITAL_ACCOUNT, "GitHub:JohnDoe", "github:johndoe"),
        (NodeType.LEGAL_CASE, "0001234-56.2023.8.26.0100", "00012345620238260100"),
        (NodeType.CPF_HASH, "sha256:" + "A" * 64, HASH),
        (
            NodeType.CPF_HASH,
            "b" * 64,
            "sha256:" + "b" * 64,
        ),
    ],
)
def test_selector_normalization_by_type(
    node_type: NodeType, raw: str, expected: str
) -> None:
    assert normalize_selector(node_type, raw) == expected


@pytest.mark.parametrize(
    ("node_type", "raw"),
    [
        (NodeType.CNPJ, "11.222.333/0001-80"),  # dígito verificador errado
        (NodeType.CNPJ, "123"),  # tamanho errado
        (NodeType.CPF_HASH, "52998224725"),  # CPF em texto claro
        (NodeType.CPF_HASH, "529.982.247-25"),
        (NodeType.EMAIL, "not-an-email"),
        (NodeType.DOMAIN, "https://example.com/path"),
        (NodeType.IP, "999.0.0.1"),
        (NodeType.COORDINATE, "91,0"),
        (NodeType.USERNAME, "john doe"),
        (NodeType.VEHICLE, "ABC123"),
        (NodeType.DIGITAL_ACCOUNT, "github"),
        (NodeType.ASN, "AS0"),
        (NodeType.PHONE, "123"),
    ],
)
def test_invalid_selectors_are_rejected(node_type: NodeType, raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_selector(node_type, raw)


def test_node_id_is_derived_and_stable_across_spellings() -> None:
    first = Node(type=NodeType.EMAIL, selector="John@Example.COM", scope_id="case-1")
    second = Node(type=NodeType.EMAIL, selector="  john@example.com ", scope_id="case-1")

    assert first.id == second.id
    assert first.id == node_id(NodeType.EMAIL, "john@example.com", "case-1")
    assert first.id.startswith("sha256:")


def test_node_id_changes_with_type_or_scope() -> None:
    base = Node(type=NodeType.HOST, selector="example.com", scope_id="case-1")
    other_scope = Node(type=NodeType.HOST, selector="example.com", scope_id="case-2")
    other_type = Node(type=NodeType.DOMAIN, selector="example.com", scope_id="case-1")

    assert len({base.id, other_scope.id, other_type.id}) == 3


def test_node_is_immutable() -> None:
    node = Node(
        type=NodeType.IP,
        selector="203.0.113.9",
        scope_id="case-1",
        attributes={"asn": 64500},
    )

    with pytest.raises(ValidationError):
        node.selector = "203.0.113.10"
    with pytest.raises(TypeError):
        node.attributes["asn"] = 1  # type: ignore[index]
    assert dict(node.attributes) == {"asn": 64500}


def test_node_rejects_supplied_id_that_disagrees_with_its_identity() -> None:
    with pytest.raises(ValidationError):
        Node(
            id="sha256:" + "f" * 64,
            type=NodeType.IP,
            selector="203.0.113.9",
            scope_id="case-1",
        )


def test_node_requires_scope() -> None:
    with pytest.raises(ValidationError):
        Node(type=NodeType.IP, selector="203.0.113.9", scope_id="")
    with pytest.raises(ValidationError):
        Node(type=NodeType.IP, selector="203.0.113.9", scope_id="   ")


def test_cpf_hash_node_is_sensitive_by_construction() -> None:
    node = Node(type=NodeType.CPF_HASH, selector=HASH, scope_id="case-1")

    assert node.sensitive is True
    assert node.requires_sensitive_store is True


def test_non_sensitive_types_are_not_forced_sensitive() -> None:
    node = Node(type=NodeType.IP, selector="203.0.113.9", scope_id="case-1")

    assert node.sensitive is False
    assert node.requires_sensitive_store is False


def test_node_serializes_frozen_attributes_as_plain_dict() -> None:
    node = Node(
        type=NodeType.ORG,
        selector="Acme",
        scope_id="case-1",
        attributes={"country": "BR"},
    )

    payload = node.model_dump()
    assert payload["attributes"] == {"country": "BR"}
    assert payload["type"] == "org"
