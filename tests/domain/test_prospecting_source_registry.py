import pytest
from pathlib import Path

from app.domain.prospecting.source_registry import (
    AcquisitionMode,
    ProspectSourceCatalog,
    ProspectSourceDefinition,
    SourceKind,
    SourceStatus,
    load_source_catalog,
)


def source(**overrides):
    values = dict(
        source_id="acate_associados",
        name="ACATE Associates",
        kind=SourceKind.ASSOCIATION_DIRECTORY,
        acquisition_mode=AcquisitionMode.OFFICIAL_EXPORT,
        status=SourceStatus.REQUIRES_TERMS_REVIEW,
        homepage="https://www.acate.com.br/associados/",
        description="Directory of technology association members.",
        yields_company_records=True,
        durable_storage_allowed=False,
    )
    values.update(overrides)
    return ProspectSourceDefinition(**values)


def test_source_catalog_does_not_treat_public_directory_as_storage_permission():
    catalog = ProspectSourceCatalog(version=1, sources=(source(),))
    assert catalog.get("acate_associados").durable_storage_allowed is False
    assert catalog.available_company_sources() == ()


def test_source_catalog_only_exposes_reviewed_sources_for_durable_company_storage():
    allowed = source(
        source_id="receita_cnpj",
        kind=SourceKind.COMPANY_REGISTRY,
        acquisition_mode=AcquisitionMode.OFFICIAL_OPEN_DATA,
        status=SourceStatus.AVAILABLE,
        durable_storage_allowed=True,
    )
    research = source(status=SourceStatus.RESEARCH_ONLY, durable_storage_allowed=False)
    catalog = ProspectSourceCatalog(version=1, sources=(allowed, research))
    assert tuple(item.source_id for item in catalog.available_company_sources()) == ("receita_cnpj",)


def test_source_catalog_rejects_duplicate_ids():
    duplicate = source()
    with pytest.raises(ValueError, match="unique"):
        ProspectSourceCatalog(version=1, sources=(duplicate, duplicate))


def test_unknown_source_is_not_silently_ignored():
    catalog = ProspectSourceCatalog(version=1, sources=(source(),))
    with pytest.raises(KeyError):
        catalog.get("unknown_source")


def test_checked_in_source_catalog_is_valid_and_includes_sources_beyond_cnpj():
    root = Path(__file__).resolve().parents[2]
    catalog = load_source_catalog(root / "config" / "prospecting" / "sources.json")

    assert catalog.get("receita_federal_cnpj_open_data").durable_storage_allowed is True
    assert catalog.get("acate_associados").durable_storage_allowed is False
    assert catalog.get("observatorio_acate").yields_aggregate_indicators is True
    assert catalog.get("pncp_compras_gov").kind is SourceKind.PROCUREMENT
    assert catalog.get("empresas_carreiras").kind is SourceKind.JOBS
