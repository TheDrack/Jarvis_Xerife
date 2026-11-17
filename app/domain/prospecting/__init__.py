"""Domain contracts and policies for B2B prospecting."""

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    ProspectRecord,
    ProspectStage,
    ProspectStageChange,
)
from app.domain.prospecting.lifecycle import (
    InvalidProspectTransition,
    transition_prospect,
)

__all__ = [
    "InvalidProspectTransition",
    "ProspectCompany",
    "ProspectEvidence",
    "ProspectEvidenceType",
    "ProspectRecord",
    "ProspectStage",
    "ProspectStageChange",
    "transition_prospect",
]
