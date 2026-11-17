import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.application.prospecting import CampaignDefinition
from app.domain.prospecting.discovery import DiscoveryQuery
from app.domain.prospecting.icp import IcpProfile, IcpWeights
from scripts.prospecto_run import main

NOW = "2026-11-17T00:00:00+00:00"


def write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="latin-1", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)
    return path


def establishment_row() -> list[str]:
    row = [""] * 29
    row[0], row[1], row[2], row[3] = "12345678", "0001", "90", "1"
    row[4], row[5], row[11], row[19], row[20] = "Alfa Obras", "02", "4120400", "SC", "8000"
    return row


def prepare_data(directory: Path, *, name: str = "Alfa Obras", basico: str = "12345678") -> None:
    row = establishment_row()
    row[0], row[4] = basico, name
    write_csv(directory / "Estabelecimentos0.csv", [row])
    write_csv(
        directory / "Empresas0.csv",
        [[basico, f"{name.upper()} LTDA", "2062", "49", "100000,00", "03", ""]],
    )
    write_csv(directory / "Municipios.csv", [["8000", "SAO JOSE"]])
    write_csv(directory / "Cnaes.csv", [["4120400", "CONSTRUCAO DE EDIFICIOS"]])


def write_campaign(path: Path) -> Path:
    tenant = uuid4()
    campaign = CampaignDefinition(
        campaign_id="cli-teste",
        name="CLI de teste",
        tenant_id=tenant,
        icp=IcpProfile(
            profile_id="cli-icp",
            name="Obras em São José",
            tenant_id=tenant,
            target_cities=("São José",),
            target_states=("SC",),
            weights=IcpWeights(territory=1.0),
            fit_threshold=100,
        ),
        query=DiscoveryQuery(uf="SC", municipalities=("São José",), cnae_prefixes=("4120",)),
    )
    path.write_text(json.dumps(campaign.model_dump(mode="json")), encoding="utf-8")
    return path


def test_cli_runs_a_campaign_and_writes_csv_and_manifest(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    campaign_path = write_campaign(tmp_path / "campaign.json")
    out_dir = tmp_path / "out"

    exit_code = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(data_dir),
            "--out",
            str(out_dir),
            "--now",
            NOW,
        ]
    )

    assert exit_code == 0
    csv_files = list(out_dir.glob("*.csv"))
    manifest_files = list(out_dir.glob("*.json"))
    assert len(csv_files) == 1 and len(manifest_files) == 1

    rows = list(csv.DictReader(csv_files[0].open(encoding="utf-8")))
    assert rows[0]["empresa"] == "Alfa Obras"
    assert rows[0]["cnpj"] == "12345678000190"

    manifest = json.loads(manifest_files[0].read_text(encoding="utf-8"))
    assert manifest["source_id"] == "receita_federal_cnpj_open_data"
    assert manifest["generated_at"] == datetime(2026, 11, 17, tzinfo=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    assert "entregues no CSV: 1" in capsys.readouterr().out
    assert manifest["query"]["include_secondary_cnae"] is True


def test_cli_records_history_and_prints_the_monthly_diff(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    campaign_path = write_campaign(tmp_path / "campaign.json")
    out_dir = tmp_path / "out"
    base = [
        "--campaign",
        str(campaign_path),
        "--data-dir",
        str(data_dir),
        "--out",
        str(out_dir),
    ]

    assert main(base + ["--now", "2026-10-17T00:00:00+00:00"]) == 0
    capsys.readouterr()

    prepare_data(data_dir, name="Beta Obras", basico="87654321")
    assert main(base + ["--now", "2026-11-17T00:00:00+00:00"]) == 0

    printed = capsys.readouterr().out
    assert "entraram: 1 | sairam: 1 | mudaram: 0 | permaneceram: 0" in printed
    assert "+ Beta Obras (87654321000190)" in printed
    assert "- Alfa Obras (12345678000190)" in printed
    assert len(list((out_dir / "history").glob("*.json"))) == 2


def test_cli_can_skip_history(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    campaign_path = write_campaign(tmp_path / "campaign.json")
    out_dir = tmp_path / "out"

    exit_code = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(data_dir),
            "--out",
            str(out_dir),
            "--now",
            NOW,
            "--no-history",
        ]
    )

    assert exit_code == 0
    assert not (out_dir / "history").exists()


def test_cli_requires_either_data_dir_or_store(tmp_path, capsys):
    campaign_path = write_campaign(tmp_path / "campaign.json")

    exit_code = main(["--campaign", str(campaign_path), "--out", str(tmp_path / "out")])

    assert exit_code == 2
    assert "--data-dir ou --store" in capsys.readouterr().err


def test_cli_can_answer_from_the_materialized_store(tmp_path):
    from app.adapters.infrastructure.prospecting import CnpjStoreBuilder, CnpjStoreFiles

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    database = tmp_path / "store.duckdb"
    CnpjStoreBuilder(database, scope_ufs=("SC",)).build(
        CnpjStoreFiles(
            establishments=(data_dir / "Estabelecimentos0.csv",),
            companies=(data_dir / "Empresas0.csv",),
            municipalities=data_dir / "Municipios.csv",
            cnaes=data_dir / "Cnaes.csv",
        )
    )
    campaign_path = write_campaign(tmp_path / "campaign.json")
    out_dir = tmp_path / "out"

    exit_code = main(
        [
            "--campaign",
            str(campaign_path),
            "--store",
            str(database),
            "--out",
            str(out_dir),
            "--now",
            NOW,
        ]
    )

    assert exit_code == 0
    rows = list(csv.DictReader(next(out_dir.glob("*.csv")).open(encoding="utf-8")))
    assert [row["empresa"] for row in rows] == ["Alfa Obras"]
    assert "answers read from the materialized store" in next(out_dir.glob("*.json")).read_text(
        encoding="utf-8"
    )


def write_catalog(path: Path) -> Path:
    payload = {
        "version": 1,
        "presets": [
            {
                "id": "obras-sao-jose",
                "name": "Obras em Sao Jose",
                "query": {
                    "uf": "SC",
                    "municipalities": ["São José"],
                    "cnae_prefixes": ["4120"],
                    "only_active": True,
                    "limit": 100,
                },
            },
            {
                "id": "software-florianopolis",
                "name": "Software em Florianopolis",
                "query": {
                    "uf": "SC",
                    "municipalities": ["São José"],
                    "cnae_prefixes": ["6201"],
                    "only_active": True,
                    "limit": 100,
                },
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_lists_available_filter_presets(tmp_path, capsys):
    catalog_path = write_catalog(tmp_path / "filters.json")

    assert main(["--list-presets", "--filters", str(catalog_path)]) == 0

    printed = capsys.readouterr().out
    assert "obras-sao-jose" in printed
    assert "software-florianopolis" in printed


def test_cli_applies_a_preset_to_the_run(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    campaign_path = write_campaign(tmp_path / "campaign.json")
    catalog_path = write_catalog(tmp_path / "filters.json")
    out_dir = tmp_path / "out"

    applied = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(data_dir),
            "--preset",
            "obras-sao-jose",
            "--filters",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--now",
            NOW,
            "--no-history",
        ]
    )
    assert applied == 0
    assert "Alfa Obras" in next(out_dir.glob("*.csv")).read_text(encoding="utf-8")

    outro = tmp_path / "out-software"
    refused = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(data_dir),
            "--preset",
            "software-florianopolis",
            "--filters",
            str(catalog_path),
            "--out",
            str(outro),
            "--now",
            NOW,
            "--no-history",
        ]
    )
    assert refused == 0
    manifest = json.loads(next(outro.glob("*.json")).read_text(encoding="utf-8"))
    assert manifest["query"]["cnae_prefixes"] == ["6201"]
    assert manifest["discovered_companies"] == 0


def test_cli_rejects_an_unknown_preset(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    campaign_path = write_campaign(tmp_path / "campaign.json")
    catalog_path = write_catalog(tmp_path / "filters.json")

    exit_code = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(data_dir),
            "--preset",
            "nao-existe",
            "--filters",
            str(catalog_path),
            "--out",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 2
    assert "unknown filter preset" in capsys.readouterr().err


def test_cli_adds_external_leads_and_marks_registry_presence(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    campaign_path = write_campaign(tmp_path / "campaign.json")
    leads_path = tmp_path / "leads.csv"
    leads_path.write_text(
        "empresa;cnpj;cidade;uf;setor;site;fonte;fonte_url\n"
        "Serralheria Indicada;;São José;SC;Serralheria;;Indicacao;https://exemplo.com/lead-1\n"
        "Fora do cadastro;99999999000199;São José;SC;Obras;;Busca web;https://exemplo.com/lead-2\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    exit_code = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(data_dir),
            "--external-leads",
            str(leads_path),
            "--external-source-url",
            "https://exemplo.com/leads",
            "--out",
            str(out_dir),
            "--now",
            NOW,
            "--no-history",
        ]
    )

    assert exit_code == 0
    rows = {
        row["empresa"]: row
        for row in csv.DictReader(next(out_dir.glob("*.csv")).open(encoding="utf-8"))
    }
    assert set(rows) == {"Alfa Obras", "Serralheria Indicada", "Fora do cadastro"}
    assert rows["Alfa Obras"]["cadastro_receita"] == "encontrado"
    assert rows["Serralheria Indicada"]["cadastro_receita"] == "nao verificado"
    assert rows["Fora do cadastro"]["cadastro_receita"] == "nao encontrado"

    manifest = json.loads(next(out_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert manifest["source_id"].endswith("+external_leads")
    assert any("external leads:" in note for note in manifest["discovery_notes"])
    assert "empresas descobertas: 3" in capsys.readouterr().out


def test_cli_requires_a_source_url_for_external_leads(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    prepare_data(data_dir)
    campaign_path = write_campaign(tmp_path / "campaign.json")
    leads_path = tmp_path / "leads.csv"
    leads_path.write_text("empresa\nAlfa\n", encoding="utf-8")

    exit_code = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(data_dir),
            "--external-leads",
            str(leads_path),
            "--out",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 2
    assert "--external-source-url" in capsys.readouterr().err


def test_cli_reports_missing_dataset_without_writing_outputs(tmp_path, capsys):
    campaign_path = write_campaign(tmp_path / "campaign.json")
    out_dir = tmp_path / "out"

    exit_code = main(
        [
            "--campaign",
            str(campaign_path),
            "--data-dir",
            str(tmp_path / "inexistente"),
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 2
    assert "erro:" in capsys.readouterr().err
    assert not out_dir.exists()
