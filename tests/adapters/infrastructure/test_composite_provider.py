from datetime import datetime, timezone
from pathlib import Path

from app.adapters.infrastructure.prospecting.composite import CompositeDiscoveryProvider
from app.adapters.infrastructure.prospecting.external_leads import ExternalLeadsAdapter
from app.domain.prospecting.contracts import (
    ProspectCompany,
    ProspectEvidence,
    RegistryPresence,
)
from app.domain.prospecting.discovery import DiscoveryQuery, DiscoveryResult

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def company(name: str, *, cnpj: str | None = None) -> ProspectCompany:
    return ProspectCompany(
        company_name=name,
        cnpj=cnpj,
        city="São José",
        state="SC",
        country="BR",
        evidence=(
            ProspectEvidence(
                source_id="test",
                source_name="Test",
                source_type="public_registry",
                url="https://exemplo.com/fonte",
                license_or_terms="Test data.",
                supports_fields=("company_name",),
                collected_at=NOW,
            ),
        ),
    )


class StubRegistry:
    source_id = "stub_registry"

    def __init__(self, pages: list[tuple[list[ProspectCompany], str | None]], known: set[str]) -> None:
        self._pages = pages
        self._known = known
        self.lookups: list[str] = []

    def discover(self, query: DiscoveryQuery, *, collected_at=None) -> DiscoveryResult:
        offset = int(query.after_cnpj_basico) if query.after_cnpj_basico else 0
        companies, cursor = self._pages[offset]
        return DiscoveryResult(
            source_id=self.source_id,
            companies=tuple(
                item.model_copy(update={"registry_presence": RegistryPresence.FOUND})
                for item in companies
            ),
            matched_rows=len(companies),
            truncated=cursor is not None,
            next_cursor=cursor,
            collected_at=collected_at or NOW,
            notes=("registry",),
        )

    def lookup_company(self, cnpj: str):
        self.lookups.append(cnpj)
        return company("Achada", cnpj=cnpj) if cnpj in self._known else None


def write_leads(path: Path) -> Path:
    path.write_text(
        "empresa;cnpj;cidade;uf;fonte_url\n"
        "Fora do cadastro;99999999000199;São José;SC;https://exemplo.com/lead-1\n"
        "Ja no resultado;12345678000190;São José;SC;https://exemplo.com/lead-2\n"
        "Sem cnpj;;São José;SC;https://exemplo.com/lead-3\n",
        encoding="utf-8",
    )
    return path


def query() -> DiscoveryQuery:
    return DiscoveryQuery(uf="SC", municipalities=("São José",), cnae_prefixes=("41",))


def test_external_leads_come_last_and_record_registry_presence(tmp_path):
    registry = StubRegistry(
        [([company("Da base", cnpj="12345678000190")], None)],
        known={"55555555000195"},
    )
    external = ExternalLeadsAdapter(write_leads(tmp_path / "leads.csv"), source_url="https://exemplo.com/leads")

    result = CompositeDiscoveryProvider(registry, external).discover(query(), collected_at=NOW)

    by_name = {item.company_name: item for item in result.companies}
    assert list(by_name) == ["Da base", "Fora do cadastro", "Sem cnpj"]
    assert by_name["Da base"].registry_presence is RegistryPresence.FOUND
    assert by_name["Fora do cadastro"].registry_presence is RegistryPresence.NOT_FOUND
    assert by_name["Sem cnpj"].registry_presence is RegistryPresence.UNVERIFIED
    assert registry.lookups == ["99999999000199"]
    assert any("2 added, 1 already present" in note for note in result.notes)


def test_known_cnpj_is_reported_as_found_even_when_outside_the_filter(tmp_path):
    registry = StubRegistry([([], None)], known={"77777777000197"})
    leads = tmp_path / "leads.csv"
    leads.write_text(
        "empresa;cnpj;cidade;uf;fonte_url\n"
        "Existe na base;77777777000197;São José;SC;https://exemplo.com/lead\n",
        encoding="utf-8",
    )

    result = CompositeDiscoveryProvider(
        registry, ExternalLeadsAdapter(leads, source_url="https://exemplo.com/leads")
    ).discover(query())

    assert result.companies[0].registry_presence is RegistryPresence.FOUND


def test_pages_keep_coming_without_external_until_the_registry_is_exhausted(tmp_path):
    first = company("Primeira", cnpj="11111111000191")
    second = company("Segunda", cnpj="22222222000192")
    registry = StubRegistry([([first], "1"), ([second], None)], known=set())
    provider = CompositeDiscoveryProvider(
        registry, ExternalLeadsAdapter(write_leads(tmp_path / "leads.csv"), source_url="https://exemplo.com/leads")
    )

    page_one = provider.discover(query())
    page_two = provider.discover(
        query().model_copy(update={"after_cnpj_basico": page_one.next_cursor})
    )

    assert [item.company_name for item in page_one.companies] == ["Primeira"]
    assert page_one.next_cursor == "1"
    assert "Fora do cadastro" in [item.company_name for item in page_two.companies]


def test_without_an_external_source_it_behaves_like_the_registry():
    registry = StubRegistry([([company("So base")], None)], known=set())

    result = CompositeDiscoveryProvider(registry).discover(query())

    assert result.source_id == "stub_registry"
    assert [item.company_name for item in result.companies] == ["So base"]
