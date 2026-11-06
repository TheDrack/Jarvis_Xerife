"""Immutable edges between graph nodes, keyed by the pivot that justifies them.

Toda aresta carrega ``selector_used``, ``source`` e ``confidence`` para que
``osint.graph.explain`` (Fase 7) seja sempre respondível. O id é derivado de
``(src, dst, pivot, selector_used, source)``: a mesma evidência vinda duas
vezes é uma aresta só.

``PivotType`` cobre infraestrutura, identidade e os pivôs brasileiros. Além dos
pivôs listados na Fase 0, estão aqui os que as Fases 3–6 exigem para expressar
suas arestas (``geo_located``, ``cidr_contains``, ``email_domain``,
``cnpj_org``, ``address_geocode``, …); sem eles o plano travaria na Fase 3.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.domain.graph.interest import Interest

if TYPE_CHECKING:  # evita ciclo de import: nodes não conhece edges
    from app.domain.graph.nodes import Node


class PivotType(str, Enum):
    """Why two nodes are connected."""

    # Infraestrutura (Fase 3)
    DNS_A = "dns_a"
    WHOIS_REGISTRANT = "whois_registrant"
    DOMAIN_OWNER = "domain_owner"
    ASN_OWNER = "asn_owner"
    CIDR_CONTAINS = "cidr_contains"
    GEO_LOCATED = "geo_located"
    SIGNAL_OBSERVED = "signal_observed"

    # Identidade (Fase 4)
    SAME_HANDLE = "same_handle"
    COMMIT_EMAIL = "commit_email"
    EMAIL_DOMAIN = "email_domain"
    EMAIL_ACCOUNT = "email_account"
    DOCUMENT_AUTHOR = "document_author"
    DOCUMENT_UNC_PATH = "document_unc_path"
    LEAK_MEMBERSHIP = "leak_membership"

    # Cadastro brasileiro (Fase 5)
    CNPJ_OWNER = "cnpj_owner"
    CNPJ_ORG = "cnpj_org"
    CNPJ_ADDRESS = "cnpj_address"
    CNPJ_PHONE = "cnpj_phone"
    ADDRESS_SHARED = "address_shared"
    ADDRESS_GEOCODE = "address_geocode"
    PHONE_OWNER = "phone_owner"

    # Judicial e governamental (Fase 6)
    PUBLIC_SERVANT = "public_servant"
    PARTY_IN_LAWSUIT = "party_in_lawsuit"
    VEHICLE_OWNER = "vehicle_owner"

    # Geoespacial genérico
    GEO_PROXIMITY = "geo_proximity"
    WIFI_BSSID = "wifi_bssid"


#: Pivôs que, sozinhos, não sustentam fusão de identidade (Fase 6).
WEAK_PIVOTS: frozenset[PivotType] = frozenset({PivotType.VEHICLE_OWNER})

#: Teto de confiança para pivôs fracos; o proprietário mascarado de um veículo
#: nunca passa disso, mesmo que o adapter informe mais.
WEAK_PIVOT_CAP = 0.4

_FIELD_SEPARATOR = "\x1f"


def edge_id(
    src: str, dst: str, pivot: PivotType, selector_used: str, source: str
) -> str:
    """Derive the canonical edge id from its evidence."""
    payload = _FIELD_SEPARATOR.join(
        (src, dst, PivotType(pivot).value, selector_used, source)
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


class Edge(BaseModel):
    """An immutable, auditable link between two nodes of the same scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default="", max_length=71)
    src: str = Field(min_length=1, max_length=71)
    dst: str = Field(min_length=1, max_length=71)
    pivot: PivotType
    selector_used: str = Field(min_length=1, max_length=512)
    source: str = Field(min_length=1, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    scope_id: str = Field(min_length=1, max_length=200)
    pivot_weak: bool = False
    interest: Interest | None = None
    attributes: Mapping[str, Any] = Field(default_factory=dict)

    @field_validator("scope_id", mode="before")
    @classmethod
    def _normalize_scope(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("scope_id must be a string")
        text = value.strip()
        if not text:
            raise ValueError("scope_id must not be blank")
        return text

    @field_validator("selector_used", "source", mode="before")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        text = value.strip()
        if not text:
            raise ValueError("value must not be blank")
        return text

    @model_validator(mode="after")
    def _derive_identity(self) -> "Edge":
        if self.src == self.dst:
            raise ValueError("an edge cannot connect a node to itself")
        expected = edge_id(self.src, self.dst, self.pivot, self.selector_used, self.source)
        if self.id and self.id != expected:
            raise ValueError(
                "edge id is derived from (src, dst, pivot, selector_used, source); "
                "it cannot be supplied"
            )
        object.__setattr__(self, "id", expected)
        if self.pivot in WEAK_PIVOTS:
            object.__setattr__(self, "pivot_weak", True)
            if self.confidence > WEAK_PIVOT_CAP:
                object.__setattr__(self, "confidence", WEAK_PIVOT_CAP)
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))
        return self

    @field_serializer("attributes")
    def _serialize_attributes(self, value: Mapping[str, Any]) -> dict[str, Any]:
        return dict(value)

    @classmethod
    def derive(
        cls,
        src: "Node",
        dst: "Node",
        pivot: PivotType,
        *,
        selector_used: str,
        source: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> "Edge":
        """Build an edge from two nodes, taking scope and confidence from them.

        Expanders must use this constructor so confidence always comes from
        the pivot table instead of an adapter's opinion.
        """
        # Import local: ``confidence`` importa ``edges`` no topo do módulo.
        from app.domain.graph.confidence import edge_confidence

        return cls(
            src=src.id,
            dst=dst.id,
            pivot=pivot,
            selector_used=selector_used,
            source=source,
            confidence=edge_confidence(src, dst, pivot),
            scope_id=src.scope_id,
            attributes=attributes or {},
        )
