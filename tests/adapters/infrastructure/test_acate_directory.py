import pytest

from app.adapters.infrastructure.prospecting.acate_directory import AcateDirectoryAdapter
from app.domain.prospecting.discovery import DiscoveryQuery


def test_acate_directory_requires_explicit_reuse_permission(tmp_path):
    with pytest.raises(PermissionError):
        AcateDirectoryAdapter(tmp_path / "members.csv")


def test_acate_directory_imports_authorized_export_with_evidence(tmp_path):
    path = tmp_path / "acate.csv"
    path.write_text(
        "Empresa;Cidade;UF;Segmento;Descricao;Site\n"
        "Empresa IA;Florianópolis;SC;AI;Automação industrial;https://example.com\n"
        "Empresa SP;São Paulo;SP;Fintech;Pagamentos;https://example.org\n",
        encoding="utf-8",
    )
    adapter = AcateDirectoryAdapter(path, reuse_permission_confirmed=True)
    result = adapter.discover(DiscoveryQuery(
        uf="SC", municipalities=("Florianópolis",), cnae_prefixes=("6201",), limit=50
    ))

    assert [company.company_name for company in result.companies] == ["Empresa IA"]
    assert result.companies[0].segment == "AI"
    assert result.companies[0].registry_presence.value == "unverified"
    assert result.companies[0].evidence[0].source_id == "acate_associados"
    assert any("not evidence" in note for note in result.notes)


def test_acate_directory_keeps_unknown_city_as_unknown_not_false_mismatch(tmp_path):
    path = tmp_path / "acate.csv"
    path.write_text("Empresa;UF\nEmpresa Sem Cidade;SC\n", encoding="utf-8")
    adapter = AcateDirectoryAdapter(path, reuse_permission_confirmed=True)
    result = adapter.discover(DiscoveryQuery(
        uf="SC", municipalities=("Florianópolis",), cnae_prefixes=("6201",)
    ))
    assert len(result.companies) == 1
    assert result.companies[0].city is None
