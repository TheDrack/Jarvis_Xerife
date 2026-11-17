from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectRecord,
    ProspectStage,
)
from app.domain.prospecting.lifecycle import InvalidProspectTransition, transition_prospect


def make_prospect() -> ProspectRecord:
    evidence = ProspectEvidence(
        source_id="company_website",
        source_name="Company website",
        source_type="company_website",
        url="https://example.com/about",
        license_or_terms="Public company information; collected for B2B prospect research.",
        supports_fields=("company_name", "website", "industry"),
        collected_at=datetime(2026, 11, 16, tzinfo=timezone.utc),
    )
    company = ProspectCompany(
        company_name="Example Industrial Ltda",
        industry="Metalworking",
        city="São José",
        state="SC",
        country="BR",
        website="https://example.com",
        evidence=(evidence,),
    )
    return ProspectRecord(
        tenant_id=uuid4(),
        company=company,
    )


def test_prospect_requires_tenant_and_traceable_company_evidence():
    prospect = make_prospect()

    assert prospect.tenant_id is not None
    assert prospect.company.evidence[0].source_id == "company_website"
    assert prospect.stage is ProspectStage.DISCOVERED


def test_company_without_source_evidence_is_rejected():
    with pytest.raises(ValidationError):
        ProspectCompany(
            company_name="Unverified Ltda",
            city="São José",
            state="SC",
            country="BR",
            evidence=(),
        )


def test_prospect_stage_transition_records_actor_reason_and_timestamp():
    prospect = make_prospect()
    changed = transition_prospect(
        prospect,
        ProspectStage.ENRICHED,
        actor_id="user-123",
        reason="Validated company profile against its official website.",
    )

    assert changed.stage is ProspectStage.ENRICHED
    assert len(changed.stage_history) == 1
    assert changed.stage_history[0].previous_stage is ProspectStage.DISCOVERED
    assert changed.stage_history[0].new_stage is ProspectStage.ENRICHED
    assert changed.stage_history[0].actor_id == "user-123"
    assert changed.stage_history[0].reason
    assert changed.stage_history[0].changed_at.tzinfo is not None
    assert prospect.stage is ProspectStage.DISCOVERED


def test_invalid_stage_transition_is_rejected():
    prospect = make_prospect()

    with pytest.raises(InvalidProspectTransition):
        transition_prospect(
            prospect,
            ProspectStage.CUSTOMER,
            actor_id="user-123",
            reason="Attempt to skip qualification and sales stages.",
        )


def test_do_not_contact_is_available_from_any_open_stage_and_is_terminal():
    prospect = make_prospect()
    suppressed = transition_prospect(
        prospect,
        ProspectStage.DO_NOT_CONTACT,
        actor_id="user-123",
        reason="Company requested no further contact.",
    )

    assert suppressed.stage is ProspectStage.DO_NOT_CONTACT
    with pytest.raises(InvalidProspectTransition):
        transition_prospect(
            suppressed,
            ProspectStage.ENRICHED,
            actor_id="user-123",
            reason="Must not reactivate a suppressed prospect.",
        )

def test_cnpj_is_normalized_to_digits():
    evidence = ProspectEvidence(
        source_id="registry",
        source_name="Public registry",
        source_type="public_registry",
        url="https://registry.example/company",
        license_or_terms="Public registry terms.",
        supports_fields=("cnpj",),
    )
    company = ProspectCompany(
        company_name="Example Ltda",
        cnpj="12.345.678/0001-90",
        evidence=(evidence,),
    )

    assert company.cnpj == "12345678000190"


def test_invalid_cnpj_length_is_rejected():
    evidence = ProspectEvidence(
        source_id="registry",
        source_name="Public registry",
        source_type="public_registry",
        url="https://registry.example/company",
        license_or_terms="Public registry terms.",
        supports_fields=("cnpj",),
    )
    with pytest.raises(ValidationError):
        ProspectCompany(
            company_name="Example Ltda",
            cnpj="123",
            evidence=(evidence,),
        )

def test_evidence_rejects_duplicate_supported_fields():
    with pytest.raises(ValidationError):
        ProspectEvidence(
            source_id="registry",
            source_name="Public registry",
            source_type="public_registry",
            url="https://registry.example/company",
            license_or_terms="Public registry terms.",
            supports_fields=("cnpj", "cnpj"),
        )
