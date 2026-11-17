from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.prospecting import (
    CampaignDefinition,
    build_snapshot,
    diff_snapshots,
    format_diff,
    load_latest_snapshot,
    run_campaign,
    save_snapshot,
)
from app.application.prospecting.history import (
    RunSnapshot,
    SnapshotChange,
    SnapshotCompany,
    company_key,
)
from app.domain.prospecting.contracts import ProspectCompany, ProspectEvidence, ProspectRecord
from app.domain.prospecting.deliverable import DeliverableRow
from app.domain.prospecting.discovery import DiscoveryQuery, DiscoveryResult
from app.domain.prospecting.icp import IcpProfile, IcpWeights

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
TENANT = uuid4()


def company(name: str, cnpj: str, *, city: str = "Florianópolis") -> ProspectCompany:
    return ProspectCompany(
        company_name=name,
        cnpj=cnpj,
        industry="CONSTRUCAO DE EDIFICIOS",
        city=city,
        state="SC",
        country="BR",
        evidence=(
            ProspectEvidence(
                source_id="receita_federal_cnpj_open_data",
                source_name="Receita Federal - Dados Abertos do CNPJ",
                source_type="public_registry",
                url="https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros/cnpj",
                license_or_terms="Creative Commons Atribuicao (CC-BY)",
                supports_fields=("company_name", "cnpj", "city"),
                collected_at=NOW - timedelta(days=1),
            ),
        ),
    )


class StubProvider:
    source_id = "stub_dataset"

    def __init__(self, companies: tuple[ProspectCompany, ...]) -> None:
        self._companies = companies

    def discover(self, query: DiscoveryQuery, *, collected_at=None) -> DiscoveryResult:
        return DiscoveryResult(
            source_id=self.source_id,
            companies=self._companies,
            collected_at=collected_at or NOW,
        )


def campaign_definition() -> CampaignDefinition:
    return CampaignDefinition(
        campaign_id="historico-teste",
        name="Histórico",
        tenant_id=TENANT,
        icp=IcpProfile(
            profile_id="historico-icp",
            name="Florianópolis",
            tenant_id=TENANT,
            target_cities=("Florianópolis",),
            target_states=("SC",),
            weights=IcpWeights(territory=1.0),
            fit_threshold=100,
        ),
        query=DiscoveryQuery(uf="SC", municipalities=("Florianópolis",), cnae_prefixes=("41",)),
    )


def snapshot_for(names_and_cnpjs: tuple[tuple[str, str], ...], *, at: datetime = NOW):
    run = run_campaign(
        StubProvider(tuple(company(name, cnpj) for name, cnpj in names_and_cnpjs)),
        campaign_definition(),
        now=at,
    )
    return build_snapshot(
        run.rows,
        campaign_id=run.manifest.campaign_id,
        source_id=run.manifest.source_id,
        generated_at=run.manifest.generated_at,
    )


def test_diff_reports_entered_and_exited_companies():
    previous = snapshot_for((("Alfa", "11111111000190"), ("Beta", "22222222000190")))
    current = snapshot_for(
        (("Alfa", "11111111000190"), ("Gama", "33333333000190")),
        at=NOW + timedelta(days=30),
    )

    diff = diff_snapshots(previous, current)

    assert [item.company_name for item in diff.entered] == ["Gama"]
    assert [item.company_name for item in diff.exited] == ["Beta"]
    assert diff.unchanged == 1
    assert "entraram: 1 | sairam: 1 | mudaram: 0 | permaneceram: 1" in format_diff(diff)
    assert "+ Gama (33333333000190)" in format_diff(diff)
    assert "- Beta (22222222000190)" in format_diff(diff)


def test_first_run_has_no_previous_and_counts_everything_as_entered():
    current = snapshot_for((("Alfa", "11111111000190"),))

    diff = diff_snapshots(None, current)

    assert diff.previous_generated_at is None
    assert len(diff.entered) == 1
    assert "primeira execucao registrada com 1 empresas" in format_diff(diff)


def test_diff_rejects_snapshots_from_different_campaigns():
    current = snapshot_for((("Alfa", "11111111000190"),))
    other = current.model_copy(update={"campaign_id": "outra"})

    with pytest.raises(ValueError):
        diff_snapshots(other, current)


def test_latest_snapshot_is_resolved_by_reference_time_not_filename(tmp_path):
    older = snapshot_for((("Alfa", "11111111000190"),))
    newer = snapshot_for((("Beta", "22222222000190"),), at=NOW + timedelta(days=30))
    save_snapshot(older, tmp_path)
    save_snapshot(newer, tmp_path)

    latest = load_latest_snapshot(tmp_path, older.campaign_id)

    assert latest is not None
    assert latest.generated_at == newer.generated_at
    assert load_latest_snapshot(tmp_path / "inexistente", older.campaign_id) is None


def test_equal_reference_time_cannot_overwrite_a_snapshot(tmp_path):
    snapshot = snapshot_for((("Alfa", "11111111000190"),))
    save_snapshot(snapshot, tmp_path)

    with pytest.raises(FileExistsError):
        save_snapshot(snapshot, tmp_path)


def entry(
    name: str,
    cnpj: str,
    *,
    fit: int = 100,
    tier: str = "outbound",
    needs_verification: bool = False,
) -> SnapshotCompany:
    return SnapshotCompany(
        key=cnpj,
        cnpj=cnpj,
        company_name=name,
        city="Florianópolis",
        state="SC",
        fit_score=fit,
        tier=tier,
        needs_verification=needs_verification,
    )


def manual_snapshot(companies: tuple[SnapshotCompany, ...], *, at: datetime = NOW) -> RunSnapshot:
    return RunSnapshot(
        campaign_id="historico-teste",
        source_id="stub_dataset",
        generated_at=at,
        companies=companies,
    )


def test_diff_reports_a_score_change_without_tier_change():
    previous = manual_snapshot((entry("Alfa", "11111111000190", fit=100),))
    current = manual_snapshot((entry("Alfa", "11111111000190", fit=80),), at=NOW + timedelta(days=30))

    diff = diff_snapshots(previous, current)

    assert len(diff.changed) == 1
    assert diff.changed[0].describe() == "fit 100 -> 80"
    assert diff.unchanged == 0
    assert "mudaram: 1" in format_diff(diff)
    assert "~ Alfa (11111111000190): fit 100 -> 80" in format_diff(diff)


def test_diff_reports_a_tier_change_and_combines_both_dimensions():
    previous = manual_snapshot((entry("Alfa", "11111111000190", fit=100, tier="outbound"),))
    current = manual_snapshot(
        (entry("Alfa", "11111111000190", fit=40, tier="not_fit"),), at=NOW + timedelta(days=30)
    )

    diff = diff_snapshots(previous, current)

    assert diff.changed[0].describe() == "fit 100 -> 40, outbound -> not_fit"
    assert len(diff.entered) == 0
    assert len(diff.exited) == 0


def test_identical_companies_are_not_reported_as_changed():
    company_entry = entry("Alfa", "11111111000190")
    previous = manual_snapshot((company_entry,))
    current = manual_snapshot((company_entry,), at=NOW + timedelta(days=30))

    diff = diff_snapshots(previous, current)

    assert diff.changed == ()
    assert diff.unchanged == 1
    assert "mudaram: 0 | permaneceram: 1" in format_diff(diff)


def test_change_rejects_entries_for_different_companies():
    with pytest.raises(ValidationError):
        SnapshotChange(
            previous=entry("Alfa", "11111111000190", fit=100),
            current=entry("Beta", "22222222000190", fit=80),
        )


def test_change_rejects_identical_entries():
    same = entry("Alfa", "11111111000190")

    with pytest.raises(ValidationError):
        SnapshotChange(previous=same, current=same)


def test_company_key_falls_back_to_normalized_name_and_city():
    assert company_key(cnpj="11.111.111/0001-90", company_name="Alfa") == "11111111000190"
    assert (
        company_key(cnpj=None, company_name="Construtora  São José", city="São José")
        == "construtora sao jose|sao jose"
    )


def test_snapshot_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RunSnapshot.model_validate(
            {
                "campaign_id": "x",
                "source_id": "y",
                "generated_at": NOW.isoformat(),
                "empresas": [],
            }
        )


def test_snapshot_excludes_not_fit_rows_by_default():
    outside = company("Fora", "99999999000190", city="Joinville")
    run = run_campaign(StubProvider((outside,)), campaign_definition(), now=NOW)

    default = build_snapshot(
        run.rows,
        campaign_id="historico-teste",
        source_id="stub_dataset",
        generated_at=NOW,
    )
    complete = build_snapshot(
        run.rows,
        campaign_id="historico-teste",
        source_id="stub_dataset",
        generated_at=NOW,
        include_unqualified=True,
    )

    assert default.companies == ()
    assert len(complete.companies) == 1


def test_rows_are_kept_on_the_run_for_history():
    run = run_campaign(StubProvider((company("Alfa", "11111111000190"),)), campaign_definition(), now=NOW)

    assert len(run.rows) == 1
    assert isinstance(run.rows[0], DeliverableRow)
    assert run.rows[0].prospect.company.company_name == "Alfa"
