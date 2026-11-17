from datetime import datetime, timedelta, timezone

from app.adapters.infrastructure.prospecting.prospecting_adapter import ProspectingAdapter
from app.adapters.infrastructure.prospecting import prospecting_adapter as adapter_module
from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    ProspectEvidenceType,
    RegistryPresence,
)
from app.domain.prospecting.discovery import DiscoveryResult
from app.runtime.toolbox import ToolAuthorizationDecision, ToolDispatcher, ToolRegistry


class ReadOnlyPolicy:
    def authorize_tool(self, request, manifest):
        return ToolAuthorizationDecision(
            granted=True,
            principal_id="prospecting-integration-test",
            session_id="prospecting-integration-session",
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            capability=request.capability or manifest.capabilities[0],
            scope=request.scope,
            operation=manifest.operation,
            approval_id=request.approval_id,
            correlation_id=request.correlation_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )


class FakeCnpjStoreProvider:
    source_id = "receita_federal_cnpj_open_data"

    def __init__(self, database):
        self.database = database

    def discover(self, query, *, collected_at=None):
        company = ProspectCompany(
            company_name="Alfa Serralheria",
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
            scanned_rows=1,
            matched_rows=1,
            collected_at=collected_at or datetime.now(timezone.utc),
        )

    def lookup_company(self, cnpj):
        return None


def test_prospecting_tool_dispatches_through_manifest_and_validates_output(
    tmp_path, monkeypatch
):
    database = tmp_path / "cnpj.duckdb"
    database.touch()
    monkeypatch.setattr(adapter_module, "CnpjStoreProvider", FakeCnpjStoreProvider)
    adapter = ProspectingAdapter(database)
    dispatcher = ToolDispatcher(
        ToolRegistry.from_file(),
        resolver=lambda adapter_id: adapter if adapter_id == "prospecting_adapter" else None,
        authorizer=ReadOnlyPolicy(),
    )

    result = dispatcher.dispatch(
        {
            "tool_id": "prospecting.companies.search",
            "arguments": {
                "uf": "SC",
                "cnae_prefixes": ["4120"],
                "municipalities": ["São José"],
                "limit": 10,
            },
            "scope": "local",
        }
    )

    assert result.success is True
    assert result.output["identity_granularity"] == "cnpj_basico"
    assert result.output["companies"][0]["cnpj"] == "12345678000190"
    assert result.output["truncated"] is False
