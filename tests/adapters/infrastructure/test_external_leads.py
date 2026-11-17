from pathlib import Path

import pytest

from app.adapters.infrastructure.prospecting.external_leads import ExternalLeadsAdapter
from app.domain.prospecting.contracts import RegistryPresence
from app.domain.prospecting.discovery import DiscoveryQuery

HEADER = "empresa;cnpj;cidade;uf;setor;site;fonte;fonte_url"


def write_leads(path: Path, rows: list[str]) -> Path:
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def adapter(path: Path) -> ExternalLeadsAdapter:
    return ExternalLeadsAdapter(path, source_url="https://exemplo.com/indicacoes")


def query(**overrides) -> DiscoveryQuery:
    values = dict(uf="SC", municipalities=("São José",), cnae_prefixes=("41",))
    values.update(overrides)
    return DiscoveryQuery(**values)


def test_reads_a_semicolon_spreadsheet_and_keeps_provenance(tmp_path):
    path = write_leads(
        tmp_path / "leads.csv",
        ["Serralheria do Bairro;12345678000190;São José;SC;Serralheria;;Indicação do cliente;https://exemplo.com/indicacao-1"],
    )

    result = adapter(path).discover(query())

    assert len(result.companies) == 1
    company = result.companies[0]
    assert company.company_name == "Serralheria do Bairro"
    assert company.cnpj == "12345678000190"
    assert company.city == "São José"
    assert company.registry_presence is RegistryPresence.UNVERIFIED
    assert str(company.evidence[0].url) == "https://exemplo.com/indicacao-1"
    assert company.evidence[0].source_type == "user_provided"
    assert any("not filtered by CNAE" in note for note in result.notes)


def test_filters_out_leads_from_other_cities_and_states(tmp_path):
    path = write_leads(
        tmp_path / "leads.csv",
        [
            "Dentro;11111111000191;São José;SC;;;;",
            "Outra cidade;22222222000192;Joinville;SC;;;;",
            "Outro estado;33333333000193;São José;PR;;;;",
        ],
    )

    result = adapter(path).discover(query())

    assert [company.company_name for company in result.companies] == ["Dentro"]


def test_lead_without_city_is_kept_and_reported(tmp_path):
    path = write_leads(tmp_path / "leads.csv", ["Sem cidade;44444444000194;;SC;;;;"])

    result = adapter(path).discover(query())

    assert [company.company_name for company in result.companies] == ["Sem cidade"]
    assert any("no city" in note for note in result.notes)


def test_malformed_cnpj_is_skipped_instead_of_breaking_the_list(tmp_path):
    path = write_leads(
        tmp_path / "leads.csv",
        ["Cnpj errado;123;São José;SC;;;;", "Certo;55555555000195;São José;SC;;;;"],
    )

    result = adapter(path).discover(query())

    assert [company.company_name for company in result.companies] == ["Certo"]
    assert result.skipped_malformed_rows == 1


def test_header_aliases_and_required_column(tmp_path):
    alias = tmp_path / "alias.csv"
    alias.write_text("nome;municipio;estado\nAlfa;São José;SC\n", encoding="utf-8")
    result = adapter(alias).discover(query())
    assert [company.company_name for company in result.companies] == ["Alfa"]

    broken = tmp_path / "broken.csv"
    broken.write_text("foo;bar\n1;2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empresa"):
        adapter(broken).discover(query())
