"""Domain contracts and policies for B2B prospecting."""

from app.domain.prospecting.market_intelligence import MarketIndicator, MarketIndicatorDataset

from app.domain.prospecting.demand import (
    CandidateType,
    DemandCandidate,
    DemandEvidence,
    DemandIntent,
    DemandMatch,
    DemandRequest,
    DemandStatus,
    MarketDirection,
    RequesterType,
    evaluate_demand_match,
)
from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    ProspectRecord,
    ProspectStage,
    ProspectStageChange,
)
from app.domain.prospecting.deliverable import (
    DELIVERABLE_CSV_HEADER,
    DeliverableRow,
    build_deliverable_csv,
    to_deliverable_records,
)
from app.domain.prospecting.discovery import (
    DiscoveryProvider,
    DiscoveryQuery,
    DiscoveryResult,
)
from app.domain.prospecting.icp import (
    CriterionEvaluation,
    CriterionOutcome,
    FitAssessment,
    FitCriterion,
    IcpProfile,
    IcpWeights,
    evaluate_fit,
)
from app.domain.prospecting.lifecycle import (
    InvalidProspectTransition,
    transition_prospect,
)
from app.domain.prospecting.qualification import (
    ConfidenceAssessment,
    IntentAssessment,
    IntentPolicy,
    IntentSignal,
    IntentSignalType,
    IntentStrength,
    QualificationAssessment,
    QualificationTier,
    assess_confidence,
    assess_intent,
    qualify_prospect,
)

__all__ = [
    "DELIVERABLE_CSV_HEADER",
    "CandidateType",
    "DemandCandidate",
    "DemandEvidence",
    "DemandIntent",
    "DemandMatch",
    "DemandRequest",
    "DemandStatus",
    "MarketDirection",
    "MarketIndicator",
    "MarketIndicatorDataset",
    "RequesterType",
    "evaluate_demand_match",
    "ConfidenceAssessment",
    "CriterionEvaluation",
    "CriterionOutcome",
    "DeliverableRow",
    "DiscoveryProvider",
    "DiscoveryQuery",
    "DiscoveryResult",
    "FitAssessment",
    "FitCriterion",
    "IcpProfile",
    "IcpWeights",
    "IntentAssessment",
    "IntentPolicy",
    "IntentSignal",
    "IntentSignalType",
    "IntentStrength",
    "InvalidProspectTransition",
    "ProspectCompany",
    "ProspectEvidence",
    "ProspectEvidenceType",
    "ProspectRecord",
    "ProspectStage",
    "ProspectStageChange",
    "QualificationAssessment",
    "QualificationTier",
    "assess_confidence",
    "assess_intent",
    "build_deliverable_csv",
    "evaluate_fit",
    "qualify_prospect",
    "to_deliverable_records",
    "transition_prospect",
]
