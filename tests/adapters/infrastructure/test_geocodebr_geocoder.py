from types import ModuleType
import sys

from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
)
from app.adapters.infrastructure.prospecting.geocodebr_geocoder import GeocodeBrGeocoder
from app.domain.prospecting.geography import GeocodingPrecision, GeocodingStatus


def company(**overrides):
    values = {
        "company_name": "Empresa Teste",
        "street_type": "RUA",
        "street_name": "DAS FLORES",
        "street_number": "100",
        "address_complement": "SALA 2",
        "neighborhood": "CENTRO",
        "postal_code": "88010000",
        "city": "SAO JOSE",
        "state": "SC",
        "evidence": (
            ProspectEvidence(
                source_id="test",
                source_name="Fixture",
                source_type=ProspectEvidenceType.USER_PROVIDED,
                url="https://example.com",
                license_or_terms="test fixture",
                supports_fields=("postal_address",),
            ),
        ),
    }
    values.update(overrides)
    return ProspectCompany(**values)


def install_fake_geocodebr(monkeypatch, rows):
    calls = {}

    class FakeFrame:
        def __init__(self, data):
            self.rows = data

    class FakeArrowTable:
        def to_pylist(self):
            return rows

    geocodebr = ModuleType("geocodebr")

    def definir_campos(**kwargs):
        calls["fields"] = kwargs
        return kwargs

    def geocode(**kwargs):
        calls["geocode"] = kwargs
        return FakeArrowTable()

    geocodebr.definir_campos = definir_campos
    geocodebr.geocode = geocode

    polars = ModuleType("polars")
    polars.DataFrame = FakeFrame
    monkeypatch.setitem(sys.modules, "geocodebr", geocodebr)
    monkeypatch.setitem(sys.modules, "polars", polars)
    return calls


def test_geocodebr_geocodes_structured_company_batch(monkeypatch):
    calls = install_fake_geocodebr(
        monkeypatch,
        [
            {
                "_jarvis_row_id": 0,
                "lat": -27.5969,
                "lon": -48.5495,
                "precisao": "numero",
                "desvio_metros": 25,
                "endereco_encontrado": "RUA DAS FLORES, 100 - CENTRO",
            }
        ],
    )

    result = GeocodeBrGeocoder().geocode_companies([company()])

    assert len(result) == 1
    assert result[0].address == company().geocoding_address
    assert result[0].status is GeocodingStatus.SUCCESS
    assert result[0].precision is GeocodingPrecision.PREMISE
    assert result[0].coordinate.latitude == -27.5969
    assert result[0].coordinate.longitude == -48.5495
    assert result[0].coordinate.accuracy_m == 25
    assert result[0].formatted_address == "RUA DAS FLORES, 100 - CENTRO"
    assert calls["fields"] == {
        "logradouro": "logradouro",
        "numero": "numero",
        "cep": "cep",
        "localidade": "localidade",
        "municipio": "municipio",
        "estado": "estado",
    }
    submitted = calls["geocode"]["enderecos"].rows[0]
    assert submitted["logradouro"] == "RUA DAS FLORES"
    assert submitted["numero"] == "100"
    assert submitted["cep"] == "88010000"
    assert submitted["localidade"] == "CENTRO"
    assert submitted["municipio"] == "SAO JOSE"
    assert submitted["estado"] == "SC"
    assert calls["geocode"]["verboso"] is False


def test_geocodebr_maps_coarse_matches_to_partial_precision(monkeypatch):
    install_fake_geocodebr(
        monkeypatch,
        [
            {
                "_jarvis_row_id": 0,
                "lat": -27.6,
                "lon": -48.6,
                "precisao": "cep",
                "desvio_metros": 800,
                "endereco_encontrado": "CEP 88010000",
            }
        ],
    )

    result = GeocodeBrGeocoder().geocode_companies([company()])[0]

    assert result.status is GeocodingStatus.PARTIAL
    assert result.precision is GeocodingPrecision.POSTAL_CODE
    assert result.coordinate.accuracy_m == 800


def test_geocodebr_returns_failed_result_when_no_match(monkeypatch):
    install_fake_geocodebr(
        monkeypatch,
        [
            {
                "_jarvis_row_id": 0,
                "lat": None,
                "lon": None,
                "precisao": None,
                "desvio_metros": None,
                "endereco_encontrado": None,
            }
        ],
    )

    result = GeocodeBrGeocoder().geocode_companies([company()])[0]

    assert result.status is GeocodingStatus.FAILED
    assert result.coordinate is None
    assert result.precision is None


def test_geocodebr_rejects_non_brazilian_company_before_loading_provider(monkeypatch):
    company_foreign = company(country="US")

    import pytest
    with pytest.raises(ValueError, match="Brazilian companies"):
        GeocodeBrGeocoder().geocode_companies([company_foreign])


def test_geocodebr_empty_batch_does_not_import_optional_dependencies():
    assert GeocodeBrGeocoder().geocode_companies([]) == []


def test_geocodebr_rejects_missing_required_municipality_before_loading_provider():
    import pytest

    with pytest.raises(ValueError, match="municipality and state"):
        GeocodeBrGeocoder().geocode_companies([company(city=None)])


def test_geocodebr_rejects_missing_required_state_before_loading_provider():
    import pytest

    with pytest.raises(ValueError, match="municipality and state"):
        GeocodeBrGeocoder().geocode_companies([company(state=None)])
