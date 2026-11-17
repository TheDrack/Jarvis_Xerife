from datetime import datetime, timezone

import pytest

from app.adapters.infrastructure.prospecting import prospecting_adapter as adapter_module
from app.adapters.infrastructure.prospecting.prospecting_adapter import ProspectingAdapter
from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    RegistryPresence,
)
from app.domain.prospecting.discovery import DiscoveryResult


class FakeCnpjStoreProvider:
    source_id = "receita_federal_cnpj_open_data"

    def __init__(self, database):
        self.database = database
        self.query = None

    def discover(self, query, *, collected_at=None):
        self.query = query
        company = ProspectCompany(
            company_name="Alfa Serralheria",
            legal_name="ALFA SERRALHERIA LTDA",
            cnpj="12345678000190",
            industry="Fabricação de estruturas metálicas",
            city="São José",
            state="SC",
            registry_presence=RegistryPresence.FOUND,
            evidence=(
                ProspectEvidence(
                    source_id=self.source_id,
                    source_name="Receita Federal - Dados Abertos do CNPJ",
                    source_type=ProspectEvidenceType.PUBLIC_REGISTRY,
                    url="https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros/cnpj",
                    license_or_terms="CC-BY; atribuição à Receita Federal.",
                    supports_fields=("company_name", "cnpj", "industry", "city", "state"),
                    collected_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
                ),
            ),
        )
        return DiscoveryResult(
            source_id=self.source_id,
            companies=(company,),
            scanned_rows=4,
            matched_rows=4,
            truncated=True,
            next_cursor="12345678",
            collected_at=collected_at or datetime(2026, 11, 17, tzinfo=timezone.utc),
            notes=("source dataset is the Receita Federal CNPJ open data",),
        )

    def lookup_company(self, cnpj):
        if cnpj != "12345678000190":
            return None
        return self.discover(
            # The lookup test only needs the company object from this deterministic fake.
            query=type("Query", (), {})()
        ).companies[0]


def test_search_companies_uses_validated_query_and_discloses_root_granularity(
    tmp_path, monkeypatch
):
    database = tmp_path / "cnpj.duckdb"
    database.touch()
    provider = FakeCnpjStoreProvider(database)
    monkeypatch.setattr(adapter_module, "CnpjStoreProvider", lambda path: provider)
    adapter = ProspectingAdapter(database)

    result = adapter.search_companies(
        uf="sc",
        municipalities=["São José"],
        cnae_prefixes=["4120", "25"],
        limit=25,
        after_cnpj_basico="00000001",
        company_sizes=["03"],
        legal_natures=["2062"],
        neighborhoods=["Trindade"],
        opened_from="20200101",
        opened_to="20251231",
        capital_min=1000,
        simples_only=True,
    )

    assert provider.query.uf == "SC"
    assert provider.query.municipalities == ("São José",)
    assert provider.query.cnae_prefixes == ("4120", "25")
    assert provider.query.after_cnpj_basico == "00000001"
    assert provider.query.company_sizes == ("03",)
    assert provider.query.legal_natures == ("2062",)
    assert provider.query.neighborhoods == ("Trindade",)
    assert provider.query.opened_from == "20200101"
    assert provider.query.capital_min == 1000
    assert provider.query.simples_only is True
    assert result["identity_granularity"] == "cnpj_basico"
    assert result["companies"][0]["cnpj"] == "12345678000190"
    assert result["truncated"] is True
    assert result["next_cursor"] == "12345678"


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_search_companies_rejects_unbounded_or_non_integer_page_sizes(
    tmp_path, monkeypatch, limit
):
    database = tmp_path / "cnpj.duckdb"
    database.touch()
    monkeypatch.setattr(adapter_module, "CnpjStoreProvider", lambda path: FakeCnpjStoreProvider(path))
    adapter = ProspectingAdapter(database)

    with pytest.raises(ValueError, match="limit"):
        adapter.search_companies(uf="SC", cnae_prefixes=["41"], limit=limit)


def test_lookup_company_requires_full_cnpj_and_returns_establishment_identity(
    tmp_path, monkeypatch
):
    database = tmp_path / "cnpj.duckdb"
    database.touch()
    monkeypatch.setattr(adapter_module, "CnpjStoreProvider", lambda path: FakeCnpjStoreProvider(path))
    adapter = ProspectingAdapter(database)

    result = adapter.lookup_company("12.345.678/0001-90")

    assert result["success"] is True
    assert result["found"] is True
    assert result["identity_granularity"] == "establishment"
    assert result["company"]["cnpj"] == "12345678000190"


def test_adapter_fails_closed_when_store_is_missing(tmp_path):
    adapter = ProspectingAdapter(tmp_path / "missing.duckdb")

    assert adapter.can_execute() is False
    with pytest.raises(FileNotFoundError, match="store unavailable"):
        adapter.search_companies(uf="SC", cnae_prefixes=["41"])


def test_relative_store_path_is_resolved_from_repository_root(monkeypatch):
    monkeypatch.setenv("JARVIS_PROSPECTO_STORE_PATH", "data/prospecting/test.duckdb")

    adapter = ProspectingAdapter()

    assert adapter.database_path.is_absolute()
    assert adapter.database_path.as_posix().endswith(
        "/data/prospecting/test.duckdb"
    )
