from pathlib import Path
from types import SimpleNamespace

from scripts import prospecto_ingest


def test_ingest_cli_discovers_optional_auxiliary_datasets(tmp_path, monkeypatch, capsys):
    data = tmp_path / "receita"
    data.mkdir()
    for name in (
        "Estabelecimentos0.csv", "Empresas0.csv", "Municipios.csv", "Cnaes.csv",
        "Simples.csv", "Naturezas.csv", "Qualificacoes.csv", "Paises.csv", "Motivos.csv",
    ):
        (data / name).write_text("", encoding="utf-8")

    captured = {}

    class FakeBuilder:
        def __init__(self, database, *, scope_ufs, memory_limit, threads):
            captured["database"] = database
            captured["scope_ufs"] = scope_ufs

        def build(self, files, *, force=False):
            captured["files"] = files
            captured["force"] = force
            return SimpleNamespace(
                database=Path("store.duckdb"),
                ingested_files=(),
                skipped_files=(),
                establishment_rows=0,
                company_rows=0,
            )

    monkeypatch.setattr(prospecto_ingest, "CnpjStoreBuilder", FakeBuilder)

    assert prospecto_ingest.main([
        "--data-dir", str(data), "--db", str(tmp_path / "store.duckdb"), "--uf", "SC"
    ]) == 0

    files = captured["files"]
    assert files.simples == data / "Simples.csv"
    assert files.legal_natures == data / "Naturezas.csv"
    assert files.qualifications == data / "Qualificacoes.csv"
    assert files.countries == data / "Paises.csv"
    assert files.situation_reasons == data / "Motivos.csv"
    assert "arquivos auxiliares opcionais: 5" in capsys.readouterr().out


def test_ingest_cli_keeps_auxiliary_files_optional(tmp_path, monkeypatch):
    data = tmp_path / "receita"
    data.mkdir()
    for name in ("Estabelecimentos0.csv", "Empresas0.csv", "Municipios.csv", "Cnaes.csv"):
        (data / name).write_text("", encoding="utf-8")

    captured = {}

    class FakeBuilder:
        def __init__(self, database, *, scope_ufs, memory_limit, threads):
            pass

        def build(self, files, *, force=False):
            captured["files"] = files
            return SimpleNamespace(
                database=Path("store.duckdb"),
                ingested_files=(),
                skipped_files=(),
                establishment_rows=0,
                company_rows=0,
            )

    monkeypatch.setattr(prospecto_ingest, "CnpjStoreBuilder", FakeBuilder)
    assert prospecto_ingest.main([
        "--data-dir", str(data), "--db", str(tmp_path / "store.duckdb"), "--uf", "SC"
    ]) == 0
    assert captured["files"].simples is None
    assert captured["files"].legal_natures is None
