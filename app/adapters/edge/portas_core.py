# -*- coding: utf-8 -*-
"""Núcleo das portas de navegador: carregamento de macros, validação e execução via CDP.

As macros são dados (JSON) com vocabulário fechado de passos. Não há interpretação de código.
O Chromium é o já aberto pelo usuário (CDP). Nenhuma ação roda na importação do módulo.
"""
from __future__ import annotations

import ipaddress
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

CDP_URL = os.environ.get("JARVIS_CDP_URL", "http://127.0.0.1:9222")


def configurar_cdp_url(url: str) -> dict[str, Any]:
    """Configura endpoint CDP local; aceita HTTP(S) ou WS(S), somente loopback."""
    global CDP_URL
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https", "ws", "wss"}:
            return {"success": False, "error": "Esquema CDP inválido; use http(s) ou ws(s)."}
        if parsed.username is not None or parsed.password is not None:
            return {"success": False, "error": "Credenciais embutidas no endpoint CDP não são permitidas."}
        host = parsed.hostname or ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host.lower() == "localhost"
        if not loopback:
            return {"success": False, "error": "CDP só pode escutar em localhost/loopback."}
        _ = parsed.port
        if not parsed.port:
            return {"success": False, "error": "Endpoint CDP precisa declarar uma porta."}
    except (TypeError, ValueError):
        return {"success": False, "error": "URL CDP inválida."}
    CDP_URL = url
    return {"success": True, "cdp_url": CDP_URL}
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
    """Accept only credential-free HTTP(S) URLs on an exact or subdomain allowlist."""
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        host = (parsed.hostname or "").rstrip(".").lower()
        if not host:
            return False
        allowed = (str(domain).strip().rstrip(".").lower() for domain in permitidos)
        return any(host == domain or host.endswith("." + domain) for domain in allowed if domain)
    except (TypeError, ValueError):
        return False


def _selecionar_pagina(contexto: Any) -> Any:
    """Prefere a aba visível; faz fallback para a última aba criada."""
    paginas = list(contexto.pages)
    if not paginas:
        return contexto.new_page()
    for pagina in reversed(paginas):
        try:
            if pagina.evaluate("document.visibilityState") == "visible":
                return pagina
        except Exception:
            continue
    return paginas[-1]


@contextmanager
def _abrir_pagina() -> Iterator[Any]:
    """Anexa ao Chromium já aberto via CDP e entrega a aba visível (ou nova)."""
    from playwright.sync_api import sync_playwright  # importação tardia

    with sync_playwright() as p:
        navegador = p.chromium.connect_over_cdp(CDP_URL)
        contexto = navegador.contexts[0]
        pagina = _selecionar_pagina(contexto)
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
