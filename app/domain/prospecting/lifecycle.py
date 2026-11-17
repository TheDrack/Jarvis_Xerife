"""Deterministic state transitions for the prospect sales pipeline."""

from __future__ import annotations

from app.domain.prospecting.contracts import (
    ProspectRecord,
    ProspectStage,
    ProspectStageChange,
)


class InvalidProspectTransition(ValueError):
    """Raised when a prospect attempts an unsupported pipeline transition."""


_ALLOWED_TRANSITIONS: dict[ProspectStage, frozenset[ProspectStage]] = {
    ProspectStage.DISCOVERED: frozenset(
        {ProspectStage.ENRICHED, ProspectStage.DISQUALIFIED}
    ),
    ProspectStage.ENRICHED: frozenset(
        {ProspectStage.QUALIFIED, ProspectStage.DISQUALIFIED}
    ),
    ProspectStage.QUALIFIED: frozenset(
        {ProspectStage.CONTACTED, ProspectStage.DISQUALIFIED}
    ),
    ProspectStage.CONTACTED: frozenset(
        {ProspectStage.ENGAGED, ProspectStage.DISQUALIFIED}
    ),
    ProspectStage.ENGAGED: frozenset(
        {
            ProspectStage.MEETING_SCHEDULED,
            ProspectStage.PROPOSAL_SENT,
            ProspectStage.DISQUALIFIED,
        }
    ),
    ProspectStage.MEETING_SCHEDULED: frozenset(
        {ProspectStage.PROPOSAL_SENT, ProspectStage.DISQUALIFIED}
    ),
    ProspectStage.PROPOSAL_SENT: frozenset(
        {ProspectStage.CUSTOMER, ProspectStage.DISQUALIFIED}
    ),
    ProspectStage.CUSTOMER: frozenset(),
    ProspectStage.DISQUALIFIED: frozenset(),
    ProspectStage.DO_NOT_CONTACT: frozenset(),
}


def transition_prospect(
    prospect: ProspectRecord,
    new_stage: ProspectStage,
    *,
    actor_id: str,
    reason: str,
) -> ProspectRecord:
    """Return a new aggregate and append an auditable stage-change event.

    Suppression is permitted from every stage and is terminal. No outreach is
    performed by this function; it only records a domain state transition.
    """
    if not actor_id.strip():
        raise ValueError("actor_id must not be empty")
    if not reason.strip():
        raise ValueError("reason must not be empty")
    if new_stage is prospect.stage:
        raise InvalidProspectTransition("Prospect is already in the requested stage")

    allowed = _ALLOWED_TRANSITIONS[prospect.stage]
    if new_stage is not ProspectStage.DO_NOT_CONTACT and new_stage not in allowed:
        raise InvalidProspectTransition(
            f"Transition from {prospect.stage.value} to {new_stage.value} is not allowed"
        )
    if prospect.stage is ProspectStage.DO_NOT_CONTACT:
        raise InvalidProspectTransition("DO_NOT_CONTACT is a terminal stage")

    change = ProspectStageChange(
        previous_stage=prospect.stage,
        new_stage=new_stage,
        actor_id=actor_id.strip(),
        reason=reason.strip(),
    )
    return prospect.model_copy(
        update={
            "stage": new_stage,
            "stage_history": (*prospect.stage_history, change),
            "updated_at": change.changed_at,
        }
    )
