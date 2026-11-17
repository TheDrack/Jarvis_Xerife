import json

import pytest

from app.adapters.infrastructure.prospecting.acate_observatory import AcateObservatoryAdapter


def indicator(**overrides):
    value = dict(
        indicator_id="floripa_tech_company_count_2025",
        source_id="observatorio_acate",
        name="Empresas de tecnologia em Florianópolis",
        value=7400,
        unit="companies",
        geography="Florianópolis",
        geography_level="municipality",
        reference_period="2025",
        published_at="2026-08-27",
        source_url="https://www.observatorioacate.com.br/florianopolis",
        methodology="Published sector indicator; preserve the original methodology and period.",
        license_or_terms="Public observatory; attribution required; confirm reuse terms.",
    )
    value.update(overrides)
    return value


def test_acate_observatory_imports_aggregate_indicators_without_company_records(tmp_path):
    path = tmp_path / "acate.json"
    path.write_text(json.dumps({"indicators": [indicator()]}), encoding="utf-8")

    dataset = AcateObservatoryAdapter(path).load()

    assert dataset.source_id == "observatorio_acate"
    assert dataset.indicators[0].value == 7400
    assert dataset.indicators[0].reference_period == "2025"
    assert dataset.indicators[0].geography == "Florianópolis"


def test_acate_observatory_rejects_source_spoofing(tmp_path):
    path = tmp_path / "acate.json"
    path.write_text(json.dumps({
        "source_id": "untrusted_source",
        "indicators": [indicator(source_id="untrusted_source")],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="source_id"):
        AcateObservatoryAdapter(path).load()


def test_acate_observatory_rejects_mixed_source_evidence(tmp_path):
    path = tmp_path / "acate.json"
    path.write_text(json.dumps({
        "indicators": [indicator(), indicator(
            indicator_id="other",
            source_id="different_source",
        )],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="match the dataset"):
        AcateObservatoryAdapter(path).load()
