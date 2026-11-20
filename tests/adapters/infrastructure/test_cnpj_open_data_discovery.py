import csv
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.adapters.infrastructure.prospecting.cnpj_open_data import (
    DATASET_LICENSE,
    CnpjOpenDataAdapter,
    CnpjOpenDataFiles,
)
from app.domain.prospecting.discovery import DiscoveryProvider, DiscoveryQuery

ESTABLISHMENT_COLUMNS = 29


def establishment(
    *,
    cnpj_basico: str = "12345678",
    ordem: str = "0001",
    dv: str = "90",
    fantasia: str = "Alfa Serralheria",
    situacao: str = "02",
    cnae: str = "4120400",
    secundario: str = "",
    uf: str = "SC",
    municipio: str = "8000",
) -> list[str]:
    row = [""] * ESTABLISHMENT_COLUMNS
    row[0] = cnpj_basico
    row[1] = ordem
    row[2] = dv
    row[3] = "1"
    row[4] = fantasia
    row[5] = situacao
    row[11] = cnae
    row[12] = secundario
    row[13], row[14], row[15], row[16] = "RUA", "DAS FLORES", "100", "SALA 2"
    row[17], row[18] = "CENTRO", "88010000"
    row[19] = uf
    row[20] = municipio
    return row


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="latin-1", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)
    return path


def build_files(tmp_path: Path, establishments: list[list[str]], companies: list[list[str]]) -> CnpjOpenDataFiles:
    return CnpjOpenDataFiles(
        establishments=write_csv(tmp_path / "Estabelecimentos0.csv", establishments),
        companies=write_csv(tmp_path / "Empresas0.csv", companies),
        municipalities=write_csv(
            tmp_path / "Municipios.csv",
            [["8000", "SAO JOSE"], ["8100", "FLORIANOPOLIS"], ["9000", "PORTO ALEGRE"]],
        ),
        cnaes=write_csv(
            tmp_path / "Cnaes.csv",
            [["4120400", "CONSTRUCAO DE EDIFICIOS"], ["6201500", "DESENVOLVIMENTO DE PROGRAMAS"]],
        ),
    )


def company_row(cnpj_basico: str = "12345678", razao: str = "ALFA SERRALHERIA LTDA") -> list[str]:
    return [cnpj_basico, razao, "2062", "49", "100000,00", "01", ""]


def query(**overrides) -> DiscoveryQuery:
    values = dict(uf="SC", municipalities=("São José",), cnae_prefixes=("4120",))
    values.update(overrides)
    return DiscoveryQuery(**values)


def test_lookup_company_presence_scans_csv_once_and_matches_full_cnpj(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[
            establishment(cnpj_basico="12345678", ordem="0001", dv="90"),
            establishment(cnpj_basico="12345678", ordem="0002", dv="07"),
            establishment(cnpj_basico="87654321", ordem="0001", dv="90"),
        ],
        companies=[company_row(), company_row("87654321", "BETA LTDA")],
    )
    adapter = CnpjOpenDataAdapter(files)
    original_rows = adapter._rows
    reads = []

    def recording_rows(path):
        reads.append(path)
        yield from original_rows(path)

    adapter._rows = recording_rows

    found = adapter.lookup_company_presence(
        ["12345678000190", "12345678000207", "99999999000199", "invalid"]
    )

    assert found == {"12345678000190", "12345678000207"}
    assert reads == [files.establishments]

def test_finds_active_company_in_the_requested_slice(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[establishment()],
        companies=[company_row()],
    )
    result = CnpjOpenDataAdapter(files).discover(query())

    assert len(result.companies) == 1
    found = result.companies[0]
    assert found.company_name == "Alfa Serralheria"
    assert found.legal_name == "ALFA SERRALHERIA LTDA"
    assert found.cnpj == "12345678000190"
    assert found.industry == "CONSTRUCAO DE EDIFICIOS"
    assert found.city == "SAO JOSE"
    assert found.state == "SC"
    assert found.street_type == "RUA"
    assert found.street_name == "DAS FLORES"
    assert found.street_number == "100"
    assert found.address_complement == "SALA 2"
    assert found.geocoding_address == "RUA DAS FLORES 100, SALA 2, CENTRO, SAO JOSE, SC, 88010000, Brasil"
    evidence = found.evidence[0]
    assert evidence.source_type == "public_registry"
    assert evidence.license_or_terms == DATASET_LICENSE
    assert "cnpj" in evidence.supports_fields
    assert "postal_address" in evidence.supports_fields
    assert len(evidence.supports_fields) <= 20
    assert result.matched_rows == 1
    assert any("CC-BY" in note for note in result.notes)


def test_ignores_inactive_other_state_other_city_and_other_activity(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[
            establishment(situacao="08"),
            establishment(cnpj_basico="20000000", uf="RS"),
            establishment(cnpj_basico="30000000", municipio="8100"),
            establishment(cnpj_basico="40000000", cnae="6201500"),
        ],
        companies=[
            company_row("20000000"),
            company_row("30000000"),
            company_row("40000000"),
        ],
    )
    result = CnpjOpenDataAdapter(files).discover(query())

    assert result.companies == ()
    assert result.matched_rows == 0


def test_keeps_one_row_per_company_and_reports_truncation(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[
            establishment(ordem="0001", fantasia="Matriz"),
            establishment(ordem="0002", fantasia="Filial"),
            establishment(cnpj_basico="87654321", fantasia="Beta Obras"),
        ],
        companies=[company_row(), company_row("87654321", "BETA OBRAS LTDA")],
    )
    adapter = CnpjOpenDataAdapter(files)

    both = adapter.discover(query(limit=10))
    assert [company.company_name for company in both.companies] == ["Matriz", "Beta Obras"]
    assert both.truncated is False

    limited = adapter.discover(query(limit=1))
    assert len(limited.companies) == 1
    assert limited.truncated is True


def test_masked_company_names_are_skipped(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[establishment(fantasia="********")],
        companies=[company_row(razao="********")],
    )
    result = CnpjOpenDataAdapter(files).discover(query())

    assert result.companies == ()
    assert result.skipped_malformed_rows == 1


def test_malformed_rows_are_counted_instead_of_crashing(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[["12345678", "0001"], establishment()],
        companies=[company_row()],
    )
    result = CnpjOpenDataAdapter(files).discover(query())

    assert len(result.companies) == 1
    assert result.skipped_malformed_rows == 1
    assert result.scanned_rows == 2


def test_unknown_municipality_yields_no_company_and_explains_it(tmp_path):
    files = build_files(tmp_path, establishments=[establishment()], companies=[company_row()])
    result = CnpjOpenDataAdapter(files).discover(query(municipalities=("Cidade Inexistente",)))

    assert result.companies == ()
    assert any("municipality" in note for note in result.notes)


def test_missing_files_raise_an_actionable_error(tmp_path):
    files = CnpjOpenDataFiles(
        establishments=tmp_path / "missing-estabelecimentos.csv",
        companies=tmp_path / "missing-empresas.csv",
        municipalities=tmp_path / "missing-municipios.csv",
        cnaes=tmp_path / "missing-cnaes.csv",
    )

    with pytest.raises(FileNotFoundError):
        CnpjOpenDataAdapter(files).discover(query())


def test_adapter_satisfies_the_discovery_provider_contract(tmp_path):
    files = build_files(tmp_path, establishments=[], companies=[])

    assert isinstance(CnpjOpenDataAdapter(files), DiscoveryProvider)


def test_secondary_activity_also_matches_by_default(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[
            establishment(cnae="4618401", secundario="4120400,4399103"),
            establishment(cnpj_basico="20000000", cnae="4618401"),
        ],
        companies=[company_row(), company_row("20000000", "BETA LTDA")],
    )
    adapter = CnpjOpenDataAdapter(files)

    matched = adapter.discover(query())
    assert [company.company_name for company in matched.companies] == ["Alfa Serralheria"]

    primary_only = adapter.discover(query(include_secondary_cnae=False))
    assert primary_only.companies == ()


def test_pagination_walks_the_whole_slice_without_repeating(tmp_path):
    rows = [establishment(cnpj_basico=f"{index:08d}", fantasia=f"Empresa {index}") for index in range(5)]
    companies = [company_row(f"{index:08d}", f"EMPRESA {index} LTDA") for index in range(5)]
    adapter = CnpjOpenDataAdapter(build_files(tmp_path, establishments=rows, companies=companies))

    first = adapter.discover(query(limit=2))
    second = adapter.discover(query(limit=2, after_cnpj_basico=first.next_cursor))
    third = adapter.discover(query(limit=2, after_cnpj_basico=second.next_cursor))

    assert [company.company_name for company in first.companies] == ["Empresa 0", "Empresa 1"]
    assert [company.company_name for company in second.companies] == ["Empresa 2", "Empresa 3"]
    assert [company.company_name for company in third.companies] == ["Empresa 4"]
    assert first.truncated is True
    assert third.next_cursor is None
    assert third.truncated is False


def test_query_rejects_invalid_cnae_and_blank_municipality():
    with pytest.raises(ValidationError):
        DiscoveryQuery(uf="SC", cnae_prefixes=("1",))
    with pytest.raises(ValidationError):
        DiscoveryQuery(uf="SC", cnae_prefixes=("4120",), municipalities=(" ",))
    with pytest.raises(ValidationError):
        DiscoveryQuery(uf="SC", cnae_prefixes=("4120",), after_cnpj_basico="123")


def test_csv_adapter_rejects_advanced_filters_it_cannot_apply(tmp_path):
    files = build_files(tmp_path, [establishment()], [company_row()])
    adapter = CnpjOpenDataAdapter(files)

    with pytest.raises(NotImplementedError, match="DuckDB"):
        adapter.discover(query(company_sizes=("03",)))


def test_lookup_company_returns_address_and_municipality_for_geocoding(tmp_path):
    files = build_files(
        tmp_path,
        establishments=[establishment()],
        companies=[company_row()],
    )

    found = CnpjOpenDataAdapter(files).lookup_company("12345678000190")

    assert found is not None
    assert found.city == "SAO JOSE"
    assert found.geocoding_address == "RUA DAS FLORES 100, SALA 2, CENTRO, SAO JOSE, SC, 88010000, Brasil"


