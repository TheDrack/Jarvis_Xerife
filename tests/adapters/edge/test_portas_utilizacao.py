from pathlib import Path

import pytest

from app.adapters.edge import portas_core
from app.adapters.edge.portas_utilizacao import executar_porta


def _macro(risco: str, passos=None):
    return {
        "nome": "teste",
        "descricao": "d",
        "risco": risco,
        "parametros": {},
        "dominios_permitidos": ["exemplo.com"],
        "passos": passos or [],
    }


@pytest.fixture(autouse=True)
def _sem_limite_de_taxa(monkeypatch):
    portas_core._ultimo_uso.clear()


def test_acao_sem_confirmacao_nao_executa(monkeypatch):
    chamado = []
    monkeypatch.setattr(portas_core, "_abrir_pagina", lambda: chamado.append(1))
    resultado = executar_porta(_macro("acao", [{"acao": "clicar", "seletor": "button"}]), {}, user_confirmed=False)
    assert resultado["status"] == "confirmation_required"
    assert chamado == []


def test_leitura_executa_sem_confirmacao(monkeypatch):
    class Pagina:
        def inner_text(self, seletor):
            return "Olá"

    from contextlib import contextmanager

    @contextmanager
    def falsa():
        yield Pagina()

    monkeypatch.setattr(portas_core, "_abrir_pagina", falsa)
    macro = _macro("leitura", [{"acao": "ler", "seletor": "h1", "saida": "titulo"}])
    assert executar_porta(macro, {}, user_confirmed=False) == {"success": True, "saidas": {"titulo": "Olá"}}


def test_dominio_fora_da_lista_e_bloqueado(monkeypatch):
    from contextlib import contextmanager

    class Pagina:
        def goto(self, url):
            raise AssertionError("não deveria navegar")

    @contextmanager
    def falsa():
        yield Pagina()

    monkeypatch.setattr(portas_core, "_abrir_pagina", falsa)
    macro = _macro("leitura", [{"acao": "goto", "valor": "https://malicioso.net"}])
    resultado = executar_porta(macro, {}, user_confirmed=False)
    assert resultado["success"] is False
    assert "domínio fora da lista" in resultado["error"]


def test_macro_de_leitura_com_clique_e_rejeitada(tmp_path: Path):
    (tmp_path / "ruim.json").write_text(
        '{"nome":"ruim","descricao":"d","risco":"leitura","parametros":{},'
        '"dominios_permitidos":[],"passos":[{"acao":"clicar","seletor":"a"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="não pode clicar"):
        portas_core.carregar_macros(tmp_path)
