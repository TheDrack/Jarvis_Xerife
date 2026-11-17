import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectRecord,
    RegistryPresence,
)
from app.domain.prospecting.deliverable import (
    DELIVERABLE_CSV_HEADER,
    DeliverableRow,
    build_deliverable_csv,
)
from app.domain.prospecting.icp import IcpProfile, IcpWeights
from app.domain.prospecting.qualification import (
    IntentSignal,
    IntentSignalType,
    qualify_prospect,
)

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
TENANT = uuid4()


def evidence(url: str = "https://example.com/about") -> ProspectEvidence:
    return ProspectEvidence(
        source_id="company_website",
        source_name="Company website",
        source_type="company_website",
        url=url,
        license_or_terms="Public company information; collected for B2B prospect research.",
        supports_fields=("company_name", "industry"),
        collected_at=NOW - timedelta(days=2),
    )


def profile() -> IcpProfile:
    return IcpProfile(
        profile_id="icp-sul",
        name="Buyers in Santa Catarina",
        tenant_id=TENANT,
        target_industries=("Comunicação Visual",),
        target_states=("SC",),
        weights=IcpWeights(industry=0.5, territory=0.5),
    )


def build(
    name: str,
    *,
    industry: str = "Comunicação Visual e Serralheria",
    state: str = "SC",
    intent: bool = False,
    intent_url: str = "https://news.example.com/expansion",
    registry_presence: RegistryPresence | None = None,
) -> DeliverableRow:
    company = ProspectCompany(
        company_name=name,
        industry=industry,
        city="São José",
        state=state,
        country="BR",
        website="https://example.com",
        registry_presence=registry_presence,
        evidence=(evidence(),),
    )
    prospect = ProspectRecord(tenant_id=TENANT, company=company)
    signals = (
        (
            IntentSignal(
                signal_type=IntentSignalType.EXPANSION,
                description="Company announced a new production line.",
                evidence=evidence(intent_url),
                observed_at=NOW - timedelta(days=4),
            ),
            IntentSignal(
                signal_type=IntentSignalType.HIRING,
                description="Company opened industrial job postings.",
                evidence=evidence("https://jobs.example.com/company"),
                observed_at=NOW - timedelta(days=6),
            ),
        )
        if intent
        else ()
    )
    return DeliverableRow(
        prospect=prospect,
        assessment=qualify_prospect(prospect, profile(), intent_signals=signals, now=NOW),
    )


def parse(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_csv_uses_the_stable_portuguese_header_and_priority_rows_come_first():
    rows = (build("Zeta Ltda"), build("Alfa Ltda", intent=True))
    parsed = parse(build_deliverable_csv(rows))

    assert tuple(parsed[0].keys()) == DELIVERABLE_CSV_HEADER
    assert [row["empresa"] for row in parsed] == ["Alfa Ltda", "Zeta Ltda"]
    assert parsed[0]["classificacao"] == "priority"
    assert parsed[1]["classificacao"] == "outbound"


def test_unqualified_companies_are_excluded_unless_requested():
    rows = (build("Dentro do ICP"), build("Fora do ICP", industry="Software", state="SP"))

    assert [row["empresa"] for row in parse(build_deliverable_csv(rows))] == ["Dentro do ICP"]

    complete = parse(build_deliverable_csv(rows, include_unqualified=True))
    assert {row["empresa"] for row in complete} == {"Dentro do ICP", "Fora do ICP"}
    assert complete[-1]["classificacao"] == "not_fit"


def test_intent_evidence_urls_are_included_as_sources():
    row = build("Com Sinal", intent=True)
    parsed = parse(build_deliverable_csv((row,)))[0]

    assert "https://news.example.com/expansion" in parsed["fontes"]
    assert parsed["intencao"] == "moderate"


def test_spreadsheet_formula_payload_is_neutralized():
    row = build('=HYPERLINK("http://evil.example","Clique")')
    parsed = parse(build_deliverable_csv((row,)))[0]

    assert parsed["empresa"].startswith("'=")


def test_registry_presence_is_explicit_in_the_deliverable():
    rows = (
        build("Da base", registry_presence=RegistryPresence.FOUND),
        build("Fora do cadastro", registry_presence=RegistryPresence.NOT_FOUND),
        build("Sem verificacao"),
    )
    parsed = {row["empresa"]: row["cadastro_receita"] for row in parse(build_deliverable_csv(rows))}

    assert parsed == {
        "Da base": "encontrado",
        "Fora do cadastro": "nao encontrado",
        "Sem verificacao": "nao verificado",
    }


def test_row_rejects_an_assessment_from_another_prospect():
    first = build("Primeira")
    second = build("Segunda")

    with pytest.raises(ValidationError):
        DeliverableRow(prospect=first.prospect, assessment=second.assessment)


def test_row_rejects_cross_tenant_pairing():
    other = IcpProfile(
        profile_id="icp-outro",
        name="Outro tenant",
        tenant_id=uuid4(),
        target_states=("SC",),
        weights=IcpWeights(territory=1.0),
    )
    row = build("Empresa")

    with pytest.raises(ValueError):
        qualify_prospect(row.prospect, other, now=NOW)
