"""Confidence in an edge, decided by the pivot and never by the adapter.

A tabela é a fonte única de verdade: adapters informam *qual* pivô usaram, não
quão confiáveis são. ``Resolver`` (Fase 1) usa ``STRONG_PIVOTS`` para decidir
quando pode derivar ``PERSON``/``ORG``.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from app.domain.graph.edges import PivotType
from app.domain.graph.nodes import Node

#: Fator base por pivô. Pivô ausente da tabela é erro de programação, coberto
#: por teste de completude.
PIVOT_FACTOR: Mapping[PivotType, float] = MappingProxyType(
    {
        # Infraestrutura
        PivotType.DNS_A: 0.85,
        PivotType.WHOIS_REGISTRANT: 0.90,
        PivotType.DOMAIN_OWNER: 0.80,
        PivotType.ASN_OWNER: 0.80,
        PivotType.CIDR_CONTAINS: 0.95,
        PivotType.GEO_LOCATED: 0.50,
        PivotType.SIGNAL_OBSERVED: 0.70,
        # Identidade
        PivotType.SAME_HANDLE: 0.60,
        PivotType.COMMIT_EMAIL: 0.70,
        PivotType.EMAIL_DOMAIN: 0.80,
        PivotType.EMAIL_ACCOUNT: 0.75,
        PivotType.DOCUMENT_AUTHOR: 0.70,
        PivotType.DOCUMENT_UNC_PATH: 0.60,
        PivotType.LEAK_MEMBERSHIP: 0.70,
        # Cadastro brasileiro
        PivotType.CNPJ_OWNER: 0.95,
        PivotType.CNPJ_ORG: 0.95,
        PivotType.CNPJ_ADDRESS: 0.80,
        PivotType.CNPJ_PHONE: 0.75,
        PivotType.ADDRESS_SHARED: 0.50,
        PivotType.ADDRESS_GEOCODE: 0.60,
        PivotType.PHONE_OWNER: 0.60,
        # Judicial e governamental
        PivotType.PUBLIC_SERVANT: 0.85,
        PivotType.PARTY_IN_LAWSUIT: 0.90,
        PivotType.VEHICLE_OWNER: 0.40,
        # Geoespacial genérico
        PivotType.GEO_PROXIMITY: 0.35,
        PivotType.WIFI_BSSID: 0.60,
    }
)

#: Pivôs fortes: um único seletor forte basta para derivar ``PERSON`` (Fase 1).
STRONG_PIVOTS: frozenset[PivotType] = frozenset(
    {
        PivotType.COMMIT_EMAIL,
        PivotType.WHOIS_REGISTRANT,
        PivotType.CNPJ_OWNER,
    }
)

#: Penalidade quando os nós pertencem a escopos diferentes. A aresta continua
#: existindo (auditável), mas não pode ser confundida com evidência do escopo.
CROSS_SCOPE_FACTOR = 0.5


def is_strong_pivot(pivot: PivotType) -> bool:
    """True when *pivot* alone may merge identities."""
    return PivotType(pivot) in STRONG_PIVOTS


def edge_confidence(src: Node, dst: Node, pivot: PivotType) -> float:
    """Confidence of linking *src* and *dst* through *pivot*.

    Determinístico: só depende do pivô e dos escopos dos nós.
    """
    factor = PIVOT_FACTOR[PivotType(pivot)]
    if src.scope_id != dst.scope_id:
        factor *= CROSS_SCOPE_FACTOR
    return round(max(0.0, min(factor, 1.0)), 4)
