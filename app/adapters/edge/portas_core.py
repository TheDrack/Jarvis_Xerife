# -*- coding: utf-8 -*-
"""Núcleo das portas de navegador: carregamento de macros, validação e execução via CDP.

As macros são dados (JSON) com vocabulário fechado de passos. Não há interpretação de código.
O Chromium é o já aberto pelo usuário (CDP). Nenhuma ação roda na importação do módulo.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

CDP_URL = "http://127.0.0.1:9222"
RISCOS_VALIDOS = {"leitura", "acao"}
ACOES_VALIDAS = {"goto", "esperar", "clicar", "digitar", "ler"}
INTERVALO_MIN_S = 2.0

_lock = threading.Lock()
_ultimo_uso: dict[str, float] = {}


def carregar_macros(macros_dir: Path) -> dict[str, dict[str, Any]]:
    """Lê e valida cada macro JSON do diretório."""
    catalogo: dict[str, dict[str, Any]] = {}
    for caminho in sorted(macros_dir.glob("*.json")):
        macro = json.loads(caminho.read_text(encoding="utf-8"))
        _validar_macro(macro, caminho.name)
        catalogo[macro["nome"]] = macro
    return catalogo


def _validar_macro(macro: dict[str, Any], origem: str) -> None:
    for campo in ("nome", "descricao", "risco", "parametros", "dominios_permitidos", "passos"):
        if campo not in macro:
            raise ValueError(f"{origem}: campo ausente '{campo}'")
    if macro["risco"] not in RISCOS_VALIDOS:
        raise ValueError(f"{origem}: risco inválido '{macro['risco']}'")
    for passo in macro["passos"]:
        if passo.get("acao") not in ACOES_VALIDAS:
            raise ValueError(f"{origem}: ação desconhecida '{passo.get('acao')}'")
    if macro["risco"] == "leitura" and any(p["acao"] in {"clicar", "digitar"} for p in macro["passos"]):
        raise ValueError(f"{origem}: macro de leitura não pode clicar ou digitar")


def _dominio_ok(url: str, permitidos: list[str]) -> bool:
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in permitidos)


@contextmanager
def _abrir_pagina() -> Iterator[Any]:
    """Anexa ao Chromium já aberto via CDP e entrega a aba atual (ou nova)."""
    from playwright.sync_api import sync_playwright  # importação tardia

    with sync_playwright() as p:
        navegador = p.chromium.connect_over_cdp(CDP_URL)
        contexto = navegador.contexts[0]
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        yield pagina


def executar(macro: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Executa os passos da macro. Levanta ValueError, PermissionError ou RuntimeError."""
    for nome, cfg in macro["parametros"].items():
        if cfg.get("obrigatorio") and nome not in params:
            raise ValueError(f"parâmetro obrigatório ausente: {nome}")

    agora = time.monotonic()
    with _lock:
        if agora - _ultimo_uso.get(macro["nome"], -INTERVALO_MIN_S) < INTERVALO_MIN_S:
            raise RuntimeError("limite de taxa: aguarde antes de repetir a porta")
        _ultimo_uso[macro["nome"]] = agora

        saidas: dict[str, str] = {}
        with _abrir_pagina() as pagina:
            for passo in macro["passos"]:
                acao = passo["acao"]
                valor = passo.get("valor", "").format(**params) if "valor" in passo else None
                if acao == "goto":
                    if not _dominio_ok(valor, macro["dominios_permitidos"]):
                        raise PermissionError(f"domínio fora da lista: {valor}")
                    pagina.goto(valor)
                elif acao == "esperar":
                    pagina.wait_for_selector(passo["seletor"], timeout=passo.get("timeout_ms", 10000))
                elif acao == "clicar":
                    pagina.click(passo["seletor"])
                elif acao == "digitar":
                    pagina.fill(passo["seletor"], valor)
                elif acao == "ler":
                    saidas[passo["saida"]] = pagina.inner_text(passo["seletor"])
        return saidas


def captura_aba_atual() -> bytes:
    """Captura PNG da aba atual sem navegar nem alterar a página."""
    with _abrir_pagina() as pagina:
        return pagina.screenshot(type="png")
