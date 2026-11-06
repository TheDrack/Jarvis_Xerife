from __future__ import annotations

import pytest

from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.graph import Graph, GraphDelta
from app.domain.graph.nodes import Node, NodeType
from app.domain.graph.resolver import AdapterBoundaryError, Resolver

SCOPE = "case-1"


def _email(selector: str = "john@acme.example", scope: str = SCOPE) -> Node:
    return Node(type=NodeType.EMAIL, selector=selector, scope_id=scope)


def _username(selector: str = "johndoe", scope: str = SCOPE) -> Node:
    return Node(type=NodeType.USERNAME, selector=selector, scope_id=scope)


def _link(
    src: Node,
    dst: Node,
    *,
    pivot: PivotType = PivotType.SAME_HANDLE,
    selector: str = "handle",
) -> Edge:
    return Edge.derive(src, dst, pivot, selector_used=selector, source="test")


def _person(delta: GraphDelta) -> Node:
    persons = [node for node in delta.nodes if node.type is NodeType.PERSON]
    assert len(persons) == 1
    return persons[0]


def _org(delta: GraphDelta) -> Node:
    orgs = [node for node in delta.nodes if node.type is NodeType.ORG]
    assert len(orgs) == 1
    return orgs[0]


def test_merge_deduplicates_nodes_and_edges() -> None:
    email, username = _email(), _username()
    link = _link(email, username)

    resolved = Resolver().merge(
        GraphDelta(nodes=(email, email), edges=(link, link))
    )

    assert len(resolved.nodes) == 1
    assert len(resolved.edges) == 1
    assert len(resolved.duplicates) == 2


def test_merge_refuses_person_and_org_from_adapters() -> None:
    resolver = Resolver()
    person = Node(type=NodeType.PERSON, selector="john", scope_id=SCOPE)
    org = Node(type=NodeType.ORG, selector="acme", scope_id=SCOPE)

    with pytest.raises(AdapterBoundaryError):
        resolver.merge(GraphDelta(nodes=(person,)))
    with pytest.raises(AdapterBoundaryError):
        resolver.merge(GraphDelta(nodes=(org,)))

    allowed = resolver.merge(GraphDelta(nodes=(person,)), allow_derived=True)
    assert allowed.nodes == (person,)


def test_two_shared_selectors_derive_a_person() -> None:
    email, username = _email(), _username()
    graph = Graph(
        nodes=(email, username),
        edges=(
            _link(email, username, selector="john@acme.example"),
            _link(username, email, selector="johndoe"),
        ),
    )

    derived = Resolver().derive_person_org(graph)
    person = _person(derived)

    assert set(person.attributes["member_ids"]) == {email.id, username.id}
    person_edges = [
        edge
        for edge in derived.edges
        if edge.src == person.id and edge.pivot is PivotType.SAME_HANDLE
    ]
    assert len(person_edges) == 2
    assert {edge.dst for edge in person_edges} == {email.id, username.id}


def test_a_single_selector_does_not_derive_a_person() -> None:
    email, username = _email(), _username()
    graph = Graph(
        nodes=(email, username),
        edges=(
            _link(email, username, selector="same"),
            _link(username, email, selector="same"),
        ),
    )

    derived = Resolver().derive_person_org(graph)

    assert [node for node in derived.nodes if node.type is NodeType.PERSON] == []


def test_a_strong_pivot_alone_derives_a_person() -> None:
    email, username = _email(), _username()
    graph = Graph(
        nodes=(email, username),
        edges=(
            _link(
                email,
                username,
                pivot=PivotType.COMMIT_EMAIL,
                selector="john@acme.example",
            ),
        ),
    )

    derived = Resolver().derive_person_org(graph)

    assert _person(derived).type is NodeType.PERSON


def test_identity_clusters_do_not_cross_scopes() -> None:
    email = _email(scope="case-1")
    username = _username(scope="case-2")
    graph = Graph(
        nodes=(email, username),
        edges=(
            _link(email, username, selector="john@acme.example"),
            _link(username, email, selector="johndoe"),
        ),
    )

    derived = Resolver().derive_person_org(graph)

    assert [node for node in derived.nodes if node.type is NodeType.PERSON] == []


def test_domain_suffixes_derive_one_org() -> None:
    root = Node(type=NodeType.DOMAIN, selector="acme.example", scope_id=SCOPE)
    sub = Node(type=NodeType.DOMAIN, selector="mail.acme.example", scope_id=SCOPE)
    graph = Graph(nodes=(root, sub))

    derived = Resolver().derive_person_org(graph)
    org = _org(derived)

    assert org.selector == "acme.example"
    owner_edges = [
        edge for edge in derived.edges if edge.pivot is PivotType.DOMAIN_OWNER
    ]
    assert len(owner_edges) == 2
    assert {edge.dst for edge in owner_edges} == {root.id, sub.id}


def test_free_mail_does_not_create_an_org() -> None:
    graph = Graph(nodes=(_email("john@gmail.com"),))

    derived = Resolver().derive_person_org(graph)

    assert derived.nodes == ()
    assert derived.edges == ()


def test_corporate_email_creates_an_org() -> None:
    email = _email("john@acme.example")
    graph = Graph(nodes=(email,))

    derived = Resolver().derive_person_org(graph)
    org = _org(derived)

    assert org.selector == "acme.example"
    edge = derived.edges[0]
    assert edge.dst == email.id
    assert edge.pivot is PivotType.EMAIL_DOMAIN


def test_asn_org_name_creates_an_org() -> None:
    asn = Node(
        type=NodeType.ASN,
        selector="AS64500",
        scope_id=SCOPE,
        attributes={"org_name": "Example ISP"},
    )
    graph = Graph(nodes=(asn,))

    derived = Resolver().derive_person_org(graph)
    org = _org(derived)

    assert org.selector == "example isp"
    assert derived.edges[0].pivot is PivotType.ASN_OWNER
    assert derived.edges[0].dst == asn.id


def test_person_links_to_org_through_corporate_email() -> None:
    email, username = _email(), _username()
    graph = Graph(
        nodes=(email, username),
        edges=(
            _link(email, username, selector="john@acme.example"),
            _link(username, email, selector="johndoe"),
        ),
    )

    derived = Resolver().derive_person_org(graph)
    person = _person(derived)
    person_edges = [
        edge
        for edge in derived.edges
        if edge.src == person.id and edge.pivot is PivotType.EMAIL_DOMAIN
    ]

    assert len(person_edges) == 1
    assert person_edges[0].dst == _org(derived).id


def test_person_links_to_org_through_cnpj_owner() -> None:
    email, username = _email(), _username()
    cnpj = Node(
        type=NodeType.CNPJ,
        selector="11.222.333/0001-81",
        scope_id=SCOPE,
        attributes={"razao_social": "Acme Ltda."},
    )
    graph = Graph(
        nodes=(email, username, cnpj),
        edges=(
            _link(email, username, selector="john@acme.example"),
            _link(username, email, selector="johndoe"),
            _link(
                cnpj,
                email,
                pivot=PivotType.CNPJ_OWNER,
                selector="11222333000181",
            ),
        ),
    )

    derived = Resolver().derive_person_org(graph)
    person = _person(derived)
    cnpj_edges = [
        edge
        for edge in derived.edges
        if edge.src == person.id and edge.pivot is PivotType.CNPJ_ORG
    ]

    assert len(cnpj_edges) == 1
    target = next(node for node in derived.nodes if node.id == cnpj_edges[0].dst)
    assert target.selector == "acme ltda."


def test_derivation_is_idempotent() -> None:
    email, username = _email(), _username()
    graph = Graph(
        nodes=(email, username),
        edges=(
            _link(email, username, selector="john@acme.example"),
            _link(username, email, selector="johndoe"),
        ),
    )
    resolver = Resolver()

    first = resolver.derive_person_org(graph)
    second = resolver.derive_person_org(graph)

    assert [node.id for node in first.nodes] == [node.id for node in second.nodes]
    assert [edge.id for edge in first.edges] == [edge.id for edge in second.edges]
