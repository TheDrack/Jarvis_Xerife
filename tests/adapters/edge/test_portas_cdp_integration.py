"""Teste de integração das portas contra um Chromium real via CDP.

Só roda quando PORTAS_CDP_URL e PORTAS_TEST_URL estão definidos (ver
.github/workflows/portas-browser-tests.yml). Sem essas variáveis, os testes são pulados.
"""
import os
from contextlib import contextmanager
from urllib.parse import urlparse

import pytest

from app.adapters.edge import portas_core
from app.adapters.edge.portas_utilizacao import executar_porta

CDP_URL = os.environ.get("PORTAS_CDP_URL")
PAGE_URL = os.environ.get("PORTAS_TEST_URL")
DOMINIOS = [urlparse(PAGE_URL).hostname] if PAGE_URL else []

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (CDP_URL and PAGE_URL), reason="defina PORTAS_CDP_URL e PORTAS_TEST_URL"),
]


@pytest.fixture(autouse=True)
def _cdp(monkeypatch):
    monkeypatch.setattr(portas_core, "CDP_URL", CDP_URL)
    portas_core._ultimo_uso.clear()


def _macro(nome, risco, passos):
    return {"nome": nome, "descricao": "integração", "risco": risco, "parametros": {},
            "dominios_permitidos": DOMINIOS, "passos": passos}


def test_leitura_retorna_titulo_da_pagina_real():
    macro = _macro("it_ler", "leitura", [
        {"acao": "goto", "valor": PAGE_URL},
        {"acao": "esperar", "seletor": "h1", "timeout_ms": 8000},
        {"acao": "ler", "seletor": "h1", "saida": "titulo"},
    ])
    resultado = executar_porta(macro, {}, user_confirmed=False)
    assert resultado == {"success": True, "saidas": {"titulo": "Título de teste"}}


def test_acao_sem_confirmacao_nao_altera_a_pagina():
    macro = _macro("it_clique_sem_ok", "acao", [
        {"acao": "goto", "valor": PAGE_URL},
        {"acao": "esperar", "seletor": "#b", "timeout_ms": 8000},
        {"acao": "clicar", "seletor": "#b"},
        {"acao": "ler", "seletor": "h1", "saida": "titulo"},
    ])
    resultado = executar_porta(macro, {}, user_confirmed=False)
    assert resultado["status"] == "confirmation_required"


def test_acao_confirmada_clica_e_le_novo_estado():
    macro = _macro("it_clique_ok", "acao", [
        {"acao": "goto", "valor": PAGE_URL},
        {"acao": "esperar", "seletor": "#b", "timeout_ms": 8000},
        {"acao": "clicar", "seletor": "#b"},
        {"acao": "ler", "seletor": "h1", "saida": "titulo"},
    ])
    resultado = executar_porta(macro, {}, user_confirmed=True)
    assert resultado == {"success": True, "saidas": {"titulo": "Salvo"}}


def test_dominio_fora_da_allowlist_e_bloqueado_antes_de_navegar():
    macro = _macro("it_dominio", "leitura", [{"acao": "goto", "valor": "https://malicioso.invalid/"}])
    resultado = executar_porta(macro, {}, user_confirmed=False)
    assert resultado["success"] is False
    assert "domínio fora da lista" in resultado["error"]


def test_captura_da_aba_atual_devolve_png():
    png = portas_core.captura_aba_atual()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_observer_captura_requisicoes_http_do_chromium():
    from app.adapters.edge.portas_observabilidade import BrowserTrafficObserver

    observer = BrowserTrafficObserver()
    started = observer.start(cdp_url=CDP_URL)
    assert started["success"] is True
    page = None
    try:
        context = observer._contexts[0]
        page = context.new_page()
        page.goto(PAGE_URL)
        page.evaluate("fetch(window.location.href)")
        events = observer.events(limit=100)["events"]
        assert any(event["type"] == "http_request" and event.get("host") == urlparse(PAGE_URL).hostname for event in events)
        assert any(event["type"] == "http_response" and event.get("status") == 200 for event in events)
    finally:
        if page is not None:
            page.close()
        observer.stop()
