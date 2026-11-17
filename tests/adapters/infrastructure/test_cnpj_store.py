import csv
from pathlib import Path

import pytest

from app.adapters.infrastructure.prospecting.cnpj_open_data import CnpjOpenDataAdapter, CnpjOpenDataFiles
from app.adapters.infrastructure.prospecting.cnpj_store import (
    CnpjStoreBuilder,
    CnpjStoreFiles,
    CnpjStoreProvider,
)
from app.domain.prospecting.contracts import RegistryPresence
from app.domain.prospecting.discovery import DiscoveryQuery

ESTABLISHMENT_COLUMNS = 30


def establishment(
    *,
    basico: str = "12345678",
    ordem: str = "0001",
    dv: str = "90",
    fantasia: str = "Alfa Serralheria",
    situacao: str = "02",
    cnae: str = "4120400",
    secundario: str = "",
    uf: str = "SC",
    municipio: str = "8000",
    abertura: str = "20200115",
    tipo: str = "1",
    bairro: str = "Centro",
    cep: str = "88010000",
) -> list[str]:
    row = [""] * ESTABLISHMENT_COLUMNS
    row[0], row[1], row[2], row[3] = basico, ordem, dv, tipo
    row[4], row[5], row[11], row[12] = fantasia, situacao, cnae, secundario
    row[10] = abertura
    row[17], row[18] = bairro, cep
    row[19], row[20] = uf, municipio
    return row


def company_row(basico: str = "12345678", razao: str = "ALFA SERRALHERIA LTDA", *, natureza: str = "2062", capital: str = "100000,00", porte: str = "03") -> list[str]:
    return [basico, razao, natureza, "49", capital, porte, ""]


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="latin-1", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)
    return path


def build_files(
    directory: Path,
    establishments: list[list[str]],
    companies: list[list[str]],
) -> CnpjStoreFiles:
    directory.mkdir(parents=True, exist_ok=True)
    return CnpjStoreFiles(
        establishments=(write_csv(directory / "Estabelecimentos0.csv", establishments),),
        companies=(write_csv(directory / "Empresas0.csv", companies),),
        municipalities=write_csv(
            directory / "Municipios.csv",
            [["8000", "SAO JOSE"], ["8100", "FLORIANOPOLIS"], ["9000", "PORTO ALEGRE"]],
        ),
        cnaes=write_csv(
            directory / "Cnaes.csv",
            [["4120400", "CONSTRUCAO DE EDIFICIOS"], ["6201500", "SOFTWARE"]],
        ),
    )


def query(**overrides) -> DiscoveryQuery:
    values = dict(uf="SC", municipalities=("São José",), cnae_prefixes=("4120",))
    values.update(overrides)
    return DiscoveryQuery(**values)


def sample_files(tmp_path: Path) -> CnpjStoreFiles:
    return build_files(
        tmp_path / "data",
        [
            establishment(),
            establishment(basico="87654321", fantasia="Beta Obras"),
            establishment(basico="55555555", fantasia="Inativa", situacao="08"),
            establishment(basico="44444444", fantasia="Outra Cidade", municipio="8100"),
            establishment(basico="33333333", fantasia="Outro Estado", uf="PR"),
            establishment(basico="22222222", fantasia="********", cnae="4120400"),
        ],
        [
            company_row(),
            company_row("87654321", "BETA OBRAS LTDA"),
            company_row("55555555", "INATIVA LTDA"),
            company_row("44444444", "OUTRA CIDADE LTDA"),
            company_row("33333333", "OUTRO ESTADO LTDA"),
            company_row("22222222", "********"),
        ],
    )


def test_build_keeps_only_the_requested_scope_and_reports_counts(tmp_path):
    files = sample_files(tmp_path)
    report = CnpjStoreBuilder(tmp_path / "store.duckdb", scope_ufs=("SC",)).build(files)

    assert report.establishment_rows == 5  # everything except the PR row
    assert report.company_rows == 5
    assert report.ingested_files == ("Estabelecimentos0.csv", "Empresas0.csv")
    assert report.skipped_files == ()


def test_store_provider_matches_the_csv_adapter(tmp_path):
    files = sample_files(tmp_path)
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)

    csv_result = CnpjOpenDataAdapter(
        CnpjOpenDataFiles(
            establishments=files.establishments[0],
            companies=files.companies[0],
            municipalities=files.municipalities,
            cnaes=files.cnaes,
        )
    ).discover(query())
    store_result = CnpjStoreProvider(database).discover(query())

    csv_companies = sorted(c.cnpj for c in csv_result.companies)
    store_companies = sorted(c.cnpj for c in store_result.companies)
    assert store_companies == csv_companies == ["12345678000190", "87654321000190"]
    assert store_result.matched_rows == csv_result.matched_rows
    assert store_result.truncated is False


def test_masked_names_and_inactive_rows_are_excluded(tmp_path):
    files = sample_files(tmp_path)
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)

    active = CnpjStoreProvider(database).discover(query())
    everything = CnpjStoreProvider(database).discover(query(only_active=False))

    assert all(not company.company_name.startswith("*") for company in active.companies)
    assert all(not company.company_name.startswith("*") for company in everything.companies)
    assert len(everything.companies) >= len(active.companies)


def test_rebuild_skips_files_already_ingested(tmp_path):
    files = sample_files(tmp_path)
    database = tmp_path / "store.duckdb"
    builder = CnpjStoreBuilder(database, scope_ufs=("SC",))

    builder.build(files)
    second = builder.build(files)

    assert second.ingested_files == ()
    assert set(second.skipped_files) == {"Estabelecimentos0.csv", "Empresas0.csv"}
    assert second.establishment_rows == 5


def test_truncation_is_reported_with_the_ordering_caveat(tmp_path):
    files = sample_files(tmp_path)
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)

    result = CnpjStoreProvider(database).discover(query(limit=1))

    assert len(result.companies) == 1
    assert result.truncated is True
    assert result.next_cursor is not None
    # matched_rows counts establishments that hit the filters, including the one
    # whose name is masked and therefore never becomes a company — same as the CSV adapter.
    assert result.matched_rows == 3
    assert any("CNPJ base order" in note for note in result.notes)


def test_unknown_municipality_returns_an_explanation(tmp_path):
    files = sample_files(tmp_path)
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)

    result = CnpjStoreProvider(database).discover(query(municipalities=("Cidade Inexistente",)))

    assert result.companies == ()
    assert any("municipality" in note for note in result.notes)


def test_missing_source_files_and_missing_database_raise(tmp_path):
    builder = CnpjStoreBuilder(tmp_path / "store.duckdb", scope_ufs=("SC",))
    empty = CnpjStoreFiles(
        establishments=(tmp_path / "nao-existe.csv",),
        companies=(tmp_path / "nao-existe2.csv",),
        municipalities=tmp_path / "nao-existe3.csv",
        cnaes=tmp_path / "nao-existe4.csv",
    )

    with pytest.raises(FileNotFoundError):
        builder.build(empty)
    with pytest.raises(FileNotFoundError):
        CnpjStoreProvider(tmp_path / "sem-store.duckdb").discover(query())


def test_secondary_activity_matches_and_can_be_disabled(tmp_path):
    files = build_files(
        tmp_path,
        [establishment(cnae="4618401", secundario="4120400,4399103")],
        [company_row()],
    )
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)
    provider = CnpjStoreProvider(database)

    assert len(provider.discover(query()).companies) == 1
    assert provider.discover(query(include_secondary_cnae=False)).companies == ()


def test_store_pages_through_the_whole_slice_like_the_csv_adapter(tmp_path):
    rows = [
        establishment(basico=f"{index:08d}", fantasia=f"Empresa {index}")
        for index in range(5)
    ]
    companies = [company_row(f"{index:08d}", f"EMPRESA {index} LTDA") for index in range(5)]
    files = build_files(tmp_path, rows, companies)
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)
    provider = CnpjStoreProvider(database)

    first = provider.discover(query(limit=2))
    second = provider.discover(query(limit=2, after_cnpj_basico=first.next_cursor))
    third = provider.discover(query(limit=2, after_cnpj_basico=second.next_cursor))

    assert [company.company_name for company in first.companies] == ["Empresa 0", "Empresa 1"]
    assert [company.company_name for company in second.companies] == ["Empresa 2", "Empresa 3"]
    assert [company.company_name for company in third.companies] == ["Empresa 4"]
    assert first.next_cursor == "00000001"
    assert third.next_cursor is None
    assert third.truncated is False


def test_lookup_finds_a_cnpj_outside_the_campaign_filter(tmp_path):
    files = sample_files(tmp_path)
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)
    provider = CnpjStoreProvider(database)

    # This establishment is in Florianópolis, outside the query slice, and the lookup
    # must still find it: existence in the registry is not the same as fitting a filter.
    found = provider.lookup_company("44444444000190")
    assert found is not None
    assert found.company_name == "Outra Cidade"
    assert found.registry_presence is RegistryPresence.FOUND
    assert found.company_size == "03"
    assert found.legal_nature == "2062"
    assert found.capital_social == "100000,00"
    assert provider.lookup_company("99999999000199") is None
    assert provider.lookup_company("123") is None


def test_scope_requires_at_least_one_state(tmp_path):
    with pytest.raises(ValueError):
        CnpjStoreBuilder(tmp_path / "store.duckdb", scope_ufs=())



def test_advanced_filters_use_company_and_establishment_columns(tmp_path):
    files = build_files(
        tmp_path,
        [establishment(bairro="Trindade", cep="88036000", abertura="20240110", tipo="1")],
        [company_row(natureza="2062", capital="250000,00", porte="03")],
    )
    database = tmp_path / "advanced.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)
    result = CnpjStoreProvider(database).discover(query(
        neighborhoods=("Trindade",),
        postal_codes=("88036-000",),
        opened_from="20240101",
        opened_to="20241231",
        establishment_types=("1",),
        company_sizes=("03",),
        legal_natures=("2062",),
        capital_min=200000,
        capital_max=300000,
    ))

    assert len(result.companies) == 1
    company = result.companies[0]
    assert company.company_size == "03"
    assert company.legal_nature == "2062"
    assert company.capital_social == "250000,00"
    assert company.opening_date == "20240110"
    assert company.neighborhood == "Trindade"
    assert company.postal_code == "88036000"


def test_simples_and_mei_filters_require_the_auxiliary_dataset(tmp_path):
    files = sample_files(tmp_path)
    database = tmp_path / "without-simples.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)

    with pytest.raises(RuntimeError, match="Simples/MEI"):
        CnpjStoreProvider(database).discover(query(simples_only=True))


def test_discovery_query_rejects_invalid_date_and_capital_ranges():
    with pytest.raises(ValueError):
        query(opened_from="2025-01-01")
    with pytest.raises(ValueError, match="capital_min"):
        query(capital_min=200, capital_max=100)


def test_simples_and_mei_filters_use_the_auxiliary_dataset(tmp_path):
    base = sample_files(tmp_path)
    files = CnpjStoreFiles(
        establishments=base.establishments,
        companies=base.companies,
        municipalities=base.municipalities,
        cnaes=base.cnaes,
        simples=write_csv(
            tmp_path / "Simples.csv",
            [
                ["12345678", "S", "20200101", "", "S", "20200101", ""],
                ["87654321", "S", "20200101", "", "N", "", ""],
            ],
        ),
    )
    database = tmp_path / "with-simples.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)
    provider = CnpjStoreProvider(database)

    simples = provider.discover(query(simples_only=True))
    mei = provider.discover(query(mei_only=True))

    assert [item.cnpj for item in simples.companies] == ["12345678000190", "87654321000190"]
    assert [item.cnpj for item in mei.companies] == ["12345678000190"]


def test_builder_ingests_company_domain_lookup_tables(tmp_path):
    base = sample_files(tmp_path)
    files = CnpjStoreFiles(
        establishments=base.establishments,
        companies=base.companies,
        municipalities=base.municipalities,
        cnaes=base.cnaes,
        legal_natures=write_csv(tmp_path / "Naturezas.csv", [["2062", "Sociedade empresária limitada"]]),
        qualifications=write_csv(tmp_path / "Qualificacoes.csv", [["49", "Sócio-administrador"]]),
        countries=write_csv(tmp_path / "Paises.csv", [["105", "Brasil"]]),
        situation_reasons=write_csv(tmp_path / "Motivos.csv", [["01", "Extinção por encerramento"]]),
    )
    database = tmp_path / "lookups.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)

    import duckdb
    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute("SELECT descricao FROM legal_natures WHERE codigo='2062'").fetchone()[0] == "Sociedade empresária limitada"
        assert connection.execute("SELECT descricao FROM qualifications WHERE codigo='49'").fetchone()[0] == "Sócio-administrador"
        assert connection.execute("SELECT descricao FROM countries WHERE codigo='105'").fetchone()[0] == "Brasil"
        assert connection.execute("SELECT descricao FROM situation_reasons WHERE codigo='01'").fetchone()[0] == "Extinção por encerramento"
    finally:
        connection.close()


def test_contact_presence_and_cadastral_status_filters_do_not_return_contact_values(tmp_path):
    row = establishment()
    row[7] = "01"
    row[9] = "105"
    row[21], row[22] = "48", "33334444"
    row[25], row[26] = "48", "33335555"
    row[27] = "CONTATO@EXEMPLO.COM"
    row[28] = "SITUACAO-ESPECIAL"
    files = build_files(tmp_path, [row], [company_row()])
    database = tmp_path / "presence.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(files)

    result = CnpjStoreProvider(database).discover(query(
        has_phone=True,
        has_email=True,
        has_fax=True,
        country_codes=("105",),
        reason_codes=("01",),
        special_situation_codes=("SITUACAO-ESPECIAL",),
    ))

    assert len(result.companies) == 1
    serialized = result.companies[0].model_dump(mode="json")
    assert "33334444" not in str(serialized)
    assert "CONTATO@EXEMPLO.COM" not in str(serialized)
    assert serialized["has_phone"] is True
    assert serialized["has_email"] is True
    assert serialized["has_fax"] is True


def test_omitting_optional_auxiliary_files_clears_stale_filter_data(tmp_path):
    base = sample_files(tmp_path / "base")
    files = CnpjStoreFiles(
        establishments=base.establishments,
        companies=base.companies,
        municipalities=base.municipalities,
        cnaes=base.cnaes,
        simples=write_csv(tmp_path / "Simples.csv", [["12345678", "S", "20200101", "", "S", "20200101", ""]]),
        legal_natures=write_csv(tmp_path / "Naturezas.csv", [["2062", "Sociedade limitada"]]),
    )
    database = tmp_path / "refresh.duckdb"
    builder = CnpjStoreBuilder(database, scope_ufs=("SC",))
    builder.build(files)
    builder.build(sample_files(tmp_path / "without_aux"))

    import duckdb
    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM simples").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM legal_natures").fetchone()[0] == 0
    finally:
        connection.close()
