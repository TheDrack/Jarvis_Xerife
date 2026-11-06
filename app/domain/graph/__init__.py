"""OSINT knowledge graph domain (Fases 0–2).

O grafo é o estado primário: adapters produzem ``Node``/``Edge`` normalizados,
o ``Resolver`` deriva ``PERSON``/``ORG`` e o ``Pruner`` aplica retenção.
"""
from app.domain.graph.confidence import (
    CROSS_SCOPE_FACTOR,
    PIVOT_FACTOR,
    STRONG_PIVOTS,
    edge_confidence,
    is_strong_pivot,
)
from app.domain.graph.edges import (
    WEAK_PIVOT_CAP,
    WEAK_PIVOTS,
    Edge,
    PivotType,
    edge_id,
)
from app.domain.graph.expander import (
    Expansion,
    ExpansionCost,
    Expander,
    ExpanderSpec,
)
from app.domain.graph.fuse import Fuse
from app.domain.graph.graph import Graph, GraphDelta, GraphIntegrityError
from app.domain.graph.interest import INTEREST_VALUES, Interest
from app.domain.graph.loop import (
    PRIORITY_BY_TYPE,
    STOP_BUDGET,
    STOP_COVERAGE_STALL,
    STOP_QUEUE_EMPTY,
    EnrichmentLoop,
    LoopPolicy,
    LoopResult,
)
from app.domain.graph.registry import (
    ExpanderRegistry,
    GapReport,
    RateLimit,
    RateLimitExceeded,
)
from app.domain.graph.nodes import (
    NORMALIZERS,
    SENSITIVE_NODE_TYPES,
    Node,
    NodeType,
    is_valid_cnpj,
    is_valid_cpf,
    node_id,
    normalize_selector,
)
from app.domain.graph.policy import (
    GraphPolicyError,
    ScopePolicy,
    ScopeViolation,
    SensitiveDataError,
    SensitivityPolicy,
)
from app.domain.graph.pruner import PrunePolicy, PruneResult, Pruner
from app.domain.graph.resolver import AdapterBoundaryError, Resolver
from app.domain.graph.sensitive_store import (
    DEFAULT_SENSITIVE_TTL,
    AccessRecord,
    InMemorySensitiveStore,
    SensitiveStore,
)

__all__ = [
    "CROSS_SCOPE_FACTOR",
    "NORMALIZERS",
    "PIVOT_FACTOR",
    "SENSITIVE_NODE_TYPES",
    "STRONG_PIVOTS",
    "WEAK_PIVOT_CAP",
    "WEAK_PIVOTS",
    "AccessRecord",
    "AdapterBoundaryError",
    "DEFAULT_SENSITIVE_TTL",
    "Edge",
    "EnrichmentLoop",
    "Expansion",
    "ExpansionCost",
    "Expander",
    "ExpanderRegistry",
    "RateLimit",
    "RateLimitExceeded",
    "ExpanderSpec",
    "Fuse",
    "GapReport",
    "INTEREST_VALUES",
    "Interest",
    "LoopPolicy",
    "LoopResult",
    "PRIORITY_BY_TYPE",
    "STOP_BUDGET",
    "STOP_COVERAGE_STALL",
    "STOP_QUEUE_EMPTY",
    "Graph",
    "GraphDelta",
    "GraphIntegrityError",
    "GraphPolicyError",
    "InMemorySensitiveStore",
    "Node",
    "NodeType",
    "PivotType",
    "ScopePolicy",
    "ScopeViolation",
    "PrunePolicy",
    "PruneResult",
    "Pruner",
    "Resolver",
    "SensitiveDataError",
    "SensitiveStore",
    "SensitivityPolicy",
    "edge_confidence",
    "edge_id",
    "is_strong_pivot",
    "is_valid_cnpj",
    "is_valid_cpf",
    "node_id",
    "normalize_selector",
]
