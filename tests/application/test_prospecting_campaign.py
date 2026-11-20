import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.prospecting import (
    CampaignDefinition,
    load_campaign,
    run_campaign,
    write_run_outputs,
)
from app.domain.prospecting.contracts import ProspectCompany, ProspectEvidence
from app.domain.prospecting.discovery import DiscoveryQuery, DiscoveryResult
from app.domain.prospecting.icp import IcpProfile, IcpWeights

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
TENANT = uuid4()
REPO_ROOT = Path(__file__).resolve().parents[2]
OUR_CAMPAIGN = REPO_ROOT / "config/prospecting/campaigns/jarvis-prospecto-grande-florianopolis.json"


def company(
    name: str,
    *,
    city: str = "Florianópolis",
    state: str = "SC",
    cnpj: str | None = None,
) -> ProspectCompany:
    evidence = ProspectEvidence(
        source_id="receita_federal_cnpj_open_data",
        source_name="Receita Federal - Dados Abertos do CNPJ",
        source_type="public_registry",
        url="https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros/cnpj",
        license_or_terms="Creative Commons Atribuicao (CC-BY)",
        supports_fields=("company_name", "cnpj", "city", "state"),
        collected_at=NOW - timedelta(days=2),
    )
    return ProspectCompany(
        company_name=name,
        cnpj=cnpj,
        industry="CONSTRUCAO DE EDIFICIOS",
        city=city,
        state=state,
        country="BR",
        evidence=(evidence,),
    )


class StubProvider:
    source_id = "stub_dataset"

    def __init__(self, companies: tuple[ProspectCompany, ...]) -> None:
        self._companies = companies

    def discover(self, query: DiscoveryQuery, *, collected_at=None) -> DiscoveryResult:
        return DiscoveryResult(
            source_id=self.source_id,
            companies=self._companies,
            scanned_rows=42,
            matched_rows=len(self._companies),
            skipped_malformed_rows=1,
            collected_at=collected_at or NOW,
            notes=("stub source",),
        )


class PagedProvider:
    """Provider that honours the cursor, so pagination can be tested for real."""

    source_id = "paged_dataset"

    def __init__(self, total: int) -> None:
        self._total = total
        self.calls: list[str | None] = []

    def discover(self, query: DiscoveryQuery, *, collected_at=None) -> DiscoveryResult:
        self.calls.append(query.after_cnpj_basico)
        # The cursor is exclusive: the next page starts after the last CNPJ base.
        start = int(query.after_cnpj_basico) + 1 if query.after_cnpj_basico else 0
        take = min(query.limit, self._total - start)
        companies = tuple(
            company(f"Empresa {index}", cnpj=f"{index:08d}000190")
            for index in range(start, start + take)
        )
        last = start + take - 1
        return DiscoveryResult(
            source_id=self.source_id,
            companies=companies,
            matched_rows=take,
            truncated=last + 1 < self._total,
            next_cursor=f"{last:08d}" if last + 1 < self._total else None,
            collected_at=collected_at or NOW,
            notes=("paged source",),
        )


def campaign_definition() -> CampaignDefinition:
    return CampaignDefinition(
        campaign_id="icp-teste",
        name="Campanha de teste",
        tenant_id=TENANT,
        icp=IcpProfile(
            profile_id="icp-teste",
            name="Empresas em Florianópolis",
            tenant_id=TENANT,
            target_cities=("Florianópolis",),
            target_states=("SC",),
            weights=IcpWeights(territory=1.0),
            fit_threshold=100,
        ),
        query=DiscoveryQuery(
            uf="SC", municipalities=("Florianópolis",), cnae_prefixes=("41",), limit=500
        ),
    )


def test_run_qualifies_candidates_and_records_the_manifest():
    run = run_campaign(
        StubProvider((company("Dentro do ICP"), company("Fora do ICP", city="Joinville"))),
        campaign_definition(),
        now=NOW,
    )

    assert run.manifest.discovered_companies == 2
    assert run.manifest.delivered_rows == 1
    assert run.manifest.excluded_not_fit == 1
    assert run.manifest.source_id == "stub_dataset"
    assert run.manifest.generated_at == NOW
    assert run.manifest.discovery_notes == ("stub source",)
    assert "Dentro do ICP" in run.csv_text
    assert "Fora do ICP" not in run.csv_text


def test_run_is_deterministic_for_the_same_inputs_and_reference_time():
    first = run_campaign(StubProvider((company("Alfa"),)), campaign_definition(), now=NOW)
    second = run_campaign(StubProvider((company("Alfa"),)), campaign_definition(), now=NOW)

    assert first.csv_text == second.csv_text
    assert first.manifest.model_dump() == second.manifest.model_dump()


def test_run_exhausts_every_page_instead_of_stopping_at_the_first():
    provider = PagedProvider(total=1200)

    run = run_campaign(provider, campaign_definition(), now=NOW, include_unqualified=True)

    assert run.manifest.pages == 3
    assert run.manifest.discovered_companies == 1200
    assert run.manifest.truncated is False
    assert provider.calls == [None, "00000499", "00000999"]
    names = {row.prospect.company.company_name for row in run.rows}
    assert len(names) == 1200


def test_max_companies_caps_the_run_and_says_so():
    provider = PagedProvider(total=1200)

    run = run_campaign(provider, campaign_definition(), now=NOW, max_companies=600)

    assert run.manifest.discovered_companies == 600
    assert run.manifest.truncated is True
    assert run.manifest.max_companies == 600
    assert run.manifest.pages == 2


def test_campaign_file_ceiling_is_used_when_the_caller_sets_none():
    campaign = campaign_definition().model_copy(update={"max_companies": 1})

    run = run_campaign(PagedProvider(total=10), campaign, now=NOW)

    assert run.manifest.discovered_companies == 1
    assert run.manifest.truncated is True


def test_include_unqualified_keeps_the_rejected_company_visible():
    run = run_campaign(
        StubProvider((company("Fora", city="Joinville"),)),
        campaign_definition(),
        now=NOW,
        include_unqualified=True,
    )

    assert run.manifest.delivered_rows == 1
    assert "Fora" in run.csv_text
    assert "not_fit" in run.csv_text


def test_outputs_are_stamped_and_never_overwrite_a_previous_run(tmp_path):
    run = run_campaign(StubProvider((company("Alfa"),)), campaign_definition(), now=NOW)
    csv_path, manifest_path = write_run_outputs(run, tmp_path)

    assert csv_path.name == "icp-teste-20261117T000000Z.csv"
    assert manifest_path.name == "icp-teste-20261117T000000Z.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["csv_filename"] == csv_path.name
    assert manifest["delivered_rows"] == 1

    with pytest.raises(FileExistsError):
        write_run_outputs(run, tmp_path)


def test_campaign_tenant_must_match_the_icp_tenant():
    with pytest.raises(ValidationError):
        CampaignDefinition(
            campaign_id="x",
            name="X",
            tenant_id=TENANT,
            icp=IcpProfile(
                profile_id="y",
                name="Y",
                tenant_id=uuid4(),
                target_states=("SC",),
                weights=IcpWeights(territory=1.0),
            ),
            query=DiscoveryQuery(uf="SC", cnae_prefixes=("41",)),
        )


def test_our_own_campaign_file_loads_and_stays_consistent():
    campaign = load_campaign(OUR_CAMPAIGN)

    assert campaign.campaign_id == "jarvis-prospecto-grande-florianopolis"
    assert campaign.icp.tenant_id == campaign.tenant_id
    assert campaign.query.uf == "SC"
    assert "46" in campaign.query.cnae_prefixes
    assert campaign.query.include_secondary_cnae is True
    assert campaign.max_companies is None, "the campaign must exhaust its filter by default"
    assert campaign.query.limit >= 100, "limit is the page size now, not the ceiling"
    assert campaign.notes, "assumptions must stay documented in the campaign file"



def test_campaign_geocodes_only_delivered_companies_and_keeps_precision():
    from app.domain.prospecting.geography import (
        AddressGeocoding,
        GeoCoordinate,
        GeocodingPrecision,
        GeocodingStatus,
    )

    class FakeGeocodingService:
        def __init__(self):
            self.companies = []

        def geocode_companies(self, companies):
            self.companies.extend(companies)
            return [
                AddressGeocoding(
                    address=company.geocoding_address,
                    status=GeocodingStatus.PARTIAL,
                    coordinate=GeoCoordinate(
                        latitude=-27.5969,
                        longitude=-48.5495,
                        accuracy_m=800,
                        crs="EPSG:4674",
                    ),
                    precision=GeocodingPrecision.POSTAL_CODE,
                    provider="fake:cnefe",
                )
                for company in companies
            ]

    qualified = company("Dentro do ICP").model_copy(
        update={
            "street_type": "RUA",
            "street_name": "DAS FLORES",
            "street_number": "100",
            "postal_code": "88010000",
        }
    )
    rejected = company("Fora do ICP", city="Joinville").model_copy(
        update={
            "street_type": "RUA",
            "street_name": "DAS FLORES",
            "street_number": "200",
        }
    )
    geocoder = FakeGeocodingService()

    run = run_campaign(
        StubProvider((qualified, rejected)),
        campaign_definition(),
        now=NOW,
        geocoding_service=geocoder,
    )

    assert [item.company_name for item in geocoder.companies] == ["Dentro do ICP"]
    assert run.manifest.geocoding_enabled is True
    assert run.manifest.geocoding_attempted == 1
    assert run.manifest.geocoding_partial == 1
    assert run.manifest.geocoding_failed == 0
    assert run.rows[0].geocoding.coordinate.crs == "EPSG:4674"
    assert "latitude" in run.csv_text
    assert "-27.5969" in run.csv_text
