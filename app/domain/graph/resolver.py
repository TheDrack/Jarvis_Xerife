"""Deduplicação estrutural e derivação de ``PERSON``/``ORG`` (Fase 1).

Nenhum adapter pode criar ``PERSON`` ou ``ORG``: ``Resolver.merge`` recusa esses
tipos e só ``derive_person_org`` os produz, a partir de evidência já presente
no grafo.

Regras implementadas:

- ``PERSON`` = cluster de ``DIGITAL_ACCOUNT``/``EMAIL``/``USERNAME`` ligados por
  ≥ 2 seletores distintos **ou** por ≥ 1 pivô forte (``commit_email``,
  ``whois_registrant``, ``cnpj_owner``). Clusters não cruzam escopos.
- ``ORG`` = cluster de ``DOMAIN`` que compartilham sufixo de domínio ou o mesmo
  ``whois_registrant``, mais domínio de e-mail corporativo, nome de ASN e razão
  social de CNPJ.
- ``PERSON → ORG`` quando há e-mail corporativo (``email_domain``) ou
  ``cnpj_owner`` para um CNPJ que já tem ORG derivada (``cnpj_org``).

Tudo é determinístico: rodar a derivação duas vezes sobre o mesmo grafo produz
exatamente os mesmos ids.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from app.domain.graph.confidence import STRONG_PIVOTS
from app.domain.graph.edges import Edge, PivotType
from app.domain.graph.graph import Graph, GraphDelta
from app.domain.graph.nodes import Node, NodeType, normalize_selector

IDENTITY_TYPES: frozenset[NodeType] = frozenset(
    {NodeType.EMAIL, NodeType.USERNAME, NodeType.DIGITAL_ACCOUNT}
)

DERIVED_TYPES: frozenset[NodeType] = frozenset({NodeType.PERSON, NodeType.ORG})

#: Domínios de e-mail pessoal: não identificam organização.
FREE_MAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "aol.com",
        "bol.com.br",
        "gmail.com",
        "googlemail.com",
        "gmx.com",
        "hotmail.com",
        "icloud.com",
        "live.com",
        "mail.com",
        "me.com",
        "outlook.com",
        "proton.me",
        "protonmail.com",
        "terra.com.br",
        "uol.com.br",
        "yahoo.com",
        "yahoo.com.br",
        "yandex.com",
    }
)

_ASN_ORG_ATTRIBUTES = ("org_name", "organization", "org", "company")
_CNPJ_ORG_ATTRIBUTES = ("razao_social", "company_name", "legal_name")


class AdapterBoundaryError(ValueError):
    """Raised when an adapter tries to create a derived node type."""


_EnsureOrg = Callable[[str, str, str], Node]
_AddMember = Callable[[Node, Node], None]


class _UnionFind:
    """Deterministic union-find: the smallest id becomes the root."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            self._parent[right_root] = left_root
        else:
            self._parent[left_root] = right_root

    def groups(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for item in self._parent:
            grouped[self.find(item)].append(item)
        return {root: sorted(members) for root, members in grouped.items()}


@dataclass
class _OrgCluster:
    node: Node
    members: set[str] = field(default_factory=set)


@dataclass
class _OrgIndex:
    clusters: list[_OrgCluster] = field(default_factory=list)
    by_member: dict[str, Node] = field(default_factory=dict)
    by_domain: dict[tuple[str, str], Node] = field(default_factory=dict)
    by_selector: dict[tuple[str, str], _OrgCluster] = field(default_factory=dict)


def _org_name(node: Node, attributes: tuple[str, ...]) -> str | None:
    for attribute in attributes:
        value = node.attributes.get(attribute)
        if isinstance(value, str) and value.strip():
            return value
    return None


class Resolver:
    """Merge adapter deltas and derive person/organization clusters."""

    def merge(self, delta: GraphDelta, *, allow_derived: bool = False) -> GraphDelta:
        """Deduplicate *delta* structurally, keyed by canonical node/edge id."""
        nodes: dict[str, Node] = {}
        edges: dict[str, Edge] = {}
        duplicates: list[str] = []

        for node in delta.nodes:
            if node.type in DERIVED_TYPES and not allow_derived:
                raise AdapterBoundaryError(
                    f"{node.type.value} nodes are derived by Resolver.derive_*; "
                    "an adapter must not create them"
                )
            if node.id in nodes:
                duplicates.append(node.id)
                continue
            nodes[node.id] = node

        for edge in delta.edges:
            if edge.id in edges:
                duplicates.append(edge.id)
                continue
            edges[edge.id] = edge

        return GraphDelta(
            nodes=tuple(sorted(nodes.values(), key=lambda node: node.id)),
            edges=tuple(sorted(edges.values(), key=lambda edge: edge.id)),
            duplicates=tuple(sorted(duplicates)),
        )

    def derive_person_org(self, graph: Graph) -> GraphDelta:
        """Return the derived PERSON/ORG nodes and edges for *graph*."""
        derived_nodes: list[Node] = []
        derived_edges: list[Edge] = []

        persons = self._derive_persons(graph, derived_nodes, derived_edges)
        org_index = self._derive_orgs(graph, derived_nodes, derived_edges)
        self._link_persons_to_orgs(graph, persons, org_index, derived_edges)

        return self.merge(
            GraphDelta(nodes=tuple(derived_nodes), edges=tuple(derived_edges)),
            allow_derived=True,
        )

    # ------------------------------------------------------------------ persons

    def _derive_persons(
        self, graph: Graph, nodes_out: list[Node], edges_out: list[Edge]
    ) -> list[tuple[Node, tuple[str, ...]]]:
        identity = {
            node.id: node for node in graph.nodes if node.type in IDENTITY_TYPES
        }
        if len(identity) < 2:
            return []

        union = _UnionFind()
        for node_id in identity:
            union.add(node_id)

        selectors: dict[tuple[str, str], set[str]] = defaultdict(set)
        strong_pairs: set[tuple[str, str]] = set()
        for edge in graph.edges:
            if edge.src not in identity or edge.dst not in identity:
                continue
            if identity[edge.src].scope_id != identity[edge.dst].scope_id:
                continue
            pair = (
                (edge.src, edge.dst)
                if edge.src < edge.dst
                else (edge.dst, edge.src)
            )
            selectors[pair].add(edge.selector_used)
            if edge.pivot in STRONG_PIVOTS:
                strong_pairs.add(pair)

        for pair, used in selectors.items():
            if len(used) >= 2 or pair in strong_pairs:
                union.union(*pair)

        persons: list[tuple[Node, tuple[str, ...]]] = []
        for member_ids in union.groups().values():
            if len(member_ids) < 2:
                continue
            members = [identity[member_id] for member_id in member_ids]
            scope_id = members[0].scope_id
            person = Node(
                type=NodeType.PERSON,
                selector=self._person_selector(members),
                scope_id=scope_id,
                attributes={
                    "derived_by": "resolver.person",
                    "member_ids": tuple(member_ids),
                },
            )
            for member in members:
                edges_out.append(
                    Edge.derive(
                        person,
                        member,
                        PivotType.SAME_HANDLE,
                        selector_used=member.selector,
                        source="resolver.person",
                    )
                )
            persons.append((person, tuple(member_ids)))
            nodes_out.append(person)
        return persons

    @staticmethod
    def _person_selector(members: list[Node]) -> str:
        """Stable anchor: the smallest e-mail, else handle, else account."""
        for node_type in (NodeType.EMAIL, NodeType.USERNAME, NodeType.DIGITAL_ACCOUNT):
            candidates = sorted(
                member.selector for member in members if member.type is node_type
            )
            if candidates:
                return candidates[0]
        return sorted(member.selector for member in members)[0]

    # --------------------------------------------------------------------- orgs

    def _derive_orgs(
        self, graph: Graph, nodes_out: list[Node], edges_out: list[Edge]
    ) -> _OrgIndex:
        index = _OrgIndex()

        def ensure_org(selector: str, scope_id: str, kind: str) -> Node:
            key = (scope_id, selector)
            cluster = index.by_selector.get(key)
            if cluster is not None:
                return cluster.node
            node = Node(
                type=NodeType.ORG,
                selector=selector,
                scope_id=scope_id,
                attributes={"derived_by": "resolver.org", "kind": kind},
            )
            cluster = _OrgCluster(node=node)
            index.by_selector[key] = cluster
            index.clusters.append(cluster)
            nodes_out.append(node)
            return node

        def add_member(org: Node, member: Node) -> None:
            cluster = index.by_selector[(org.scope_id, org.selector)]
            if member.id in cluster.members:
                return
            cluster.members.add(member.id)
            index.by_member[member.id] = org

        self._derive_domain_orgs(graph, ensure_org, add_member, edges_out, index)

        for node in graph.nodes:
            if node.type is not NodeType.EMAIL:
                continue
            domain = node.selector.rsplit("@", 1)[-1]
            if domain in FREE_MAIL_DOMAINS:
                continue
            org = index.by_domain.get((node.scope_id, domain))
            if org is None:
                org = ensure_org(domain, node.scope_id, "email_domain")
                index.by_domain[(node.scope_id, domain)] = org
            add_member(org, node)
            edges_out.append(
                Edge.derive(
                    org,
                    node,
                    PivotType.EMAIL_DOMAIN,
                    selector_used=domain,
                    source="resolver.org",
                )
            )

        for node in graph.nodes:
            if node.type is NodeType.ASN:
                name = _org_name(node, _ASN_ORG_ATTRIBUTES)
                pivot = PivotType.ASN_OWNER
            elif node.type is NodeType.CNPJ:
                name = _org_name(node, _CNPJ_ORG_ATTRIBUTES)
                pivot = PivotType.CNPJ_ORG
            else:
                continue
            if name is None:
                continue
            selector = normalize_selector(NodeType.ORG, name)
            org = ensure_org(selector, node.scope_id, "registry")
            add_member(org, node)
            edges_out.append(
                Edge.derive(
                    org,
                    node,
                    pivot,
                    selector_used=selector,
                    source="resolver.org",
                )
            )

        return index

    def _derive_domain_orgs(
        self,
        graph: Graph,
        ensure_org: _EnsureOrg,
        add_member: _AddMember,
        edges_out: list[Edge],
        index: _OrgIndex,
    ) -> None:
        domains = [node for node in graph.nodes if node.type is NodeType.DOMAIN]
        if not domains:
            return

        by_selector = {node.selector: node for node in domains}
        union = _UnionFind()
        for node in domains:
            union.add(node.id)

        for node in domains:
            labels = node.selector.split(".")
            for position in range(1, len(labels) - 1):
                parent = by_selector.get(".".join(labels[position:]))
                if parent is not None and parent.scope_id == node.scope_id:
                    union.union(node.id, parent.id)

        registrants: dict[tuple[str, str], list[Node]] = defaultdict(list)
        for node in domains:
            registrant = node.attributes.get("whois_registrant")
            if isinstance(registrant, str) and registrant.strip():
                registrants[(node.scope_id, registrant.strip().casefold())].append(node)
        for group in registrants.values():
            for node in group[1:]:
                union.union(group[0].id, node.id)

        by_id = {node.id: node for node in domains}
        for member_ids in union.groups().values():
            members = [by_id[member_id] for member_id in member_ids]
            selector = min(
                (member.selector for member in members),
                key=lambda value: (len(value.split(".")), len(value), value),
            )
            org = ensure_org(selector, members[0].scope_id, "domain")
            for member in members:
                if member.scope_id != org.scope_id:
                    continue
                add_member(org, member)
                index.by_domain[(member.scope_id, member.selector)] = org
                edges_out.append(
                    Edge.derive(
                        org,
                        member,
                        PivotType.DOMAIN_OWNER,
                        selector_used=org.selector,
                        source="resolver.org",
                    )
                )

    # ------------------------------------------------------------ person → org

    def _link_persons_to_orgs(
        self,
        graph: Graph,
        persons: list[tuple[Node, tuple[str, ...]]],
        index: _OrgIndex,
        edges_out: list[Edge],
    ) -> None:
        if not persons:
            return
        nodes_by_id = {node.id: node for node in graph.nodes}

        for person, member_ids in persons:
            members = [nodes_by_id[member_id] for member_id in member_ids]
            for member in members:
                if member.type is not NodeType.EMAIL:
                    continue
                domain = member.selector.rsplit("@", 1)[-1]
                org = index.by_domain.get((member.scope_id, domain))
                if org is not None:
                    edges_out.append(
                        Edge.derive(
                            person,
                            org,
                            PivotType.EMAIL_DOMAIN,
                            selector_used=domain,
                            source="resolver.person_org",
                        )
                    )

            for edge in graph.edges:
                if edge.pivot is not PivotType.CNPJ_OWNER:
                    continue
                if edge.src in member_ids:
                    other = edge.dst
                elif edge.dst in member_ids:
                    other = edge.src
                else:
                    continue
                org = index.by_member.get(other)
                node = nodes_by_id.get(other)
                if org is None or node is None or node.type is not NodeType.CNPJ:
                    continue
                edges_out.append(
                    Edge.derive(
                        person,
                        org,
                        PivotType.CNPJ_ORG,
                        selector_used=node.selector,
                        source="resolver.person_org",
                    )
                )
