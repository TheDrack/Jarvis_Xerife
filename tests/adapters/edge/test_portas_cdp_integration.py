[Reading 202 lines from start (total: 202 lines, 0 remaining)]

"""Teste de integração das portas contra um Chromium real via CDP.

Só roda quando PORTAS_CDP_URL e PORTAS_TEST_URL estão definidos (ver
.github/workflows/portas-browser-tests.yml). Sem essas variáveis, os testes são pulados.
"""
import os
import base64
import hashlib
import socketserver
import threading
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
    from playwright.sync_api import sync_playwright
    from app.adapters.edge.portas_observabilidade import BrowserTrafficObserver

    observer = BrowserTrafficObserver()
    started = observer.start(cdp_url=CDP_URL)
    assert started["success"] is True
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.new_page()
            try:
                page.goto(PAGE_URL)
                page.evaluate("fetch(window.location.href)")
                events = observer.events(limit=100)["events"]
                assert any(event["type"] == "http_request" and event.get("host") == urlparse(PAGE_URL).hostname for event in events)
                assert any(event["type"] == "http_response" and event.get("status") == 200 for event in events)
            finally:
                page.close()
    finally:
        observer.stop()
class _WebSocketEchoHandler(socketserver.BaseRequestHandler):
    def _recv_exact(self, size):
        chunks = bytearray()
        while len(chunks) < size:
            part = self.request.recv(size - len(chunks))
            if not part:
                raise ConnectionError("websocket client disconnected")
            chunks.extend(part)
        return bytes(chunks)

    def handle(self):
        request = bytearray()
        while b"\r\n\r\n" not in request:
            request.extend(self.request.recv(4096))
        headers = {}
        for line in bytes(request).split(b"\r\n")[1:]:
            if b":" in line:
                key, value = line.split(b":", 1)
                headers[key.strip().lower()] = value.strip()
        key = headers[b"sec-websocket-key"]
        accept = base64.b64encode(
            hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
        )
        self.request.sendall(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n"
        )
        while True:
            first, second = self._recv_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(self._recv_exact(2), "big")
            elif length == 127:
                length = int.from_bytes(self._recv_exact(8), "big")
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 8:
                return
            if opcode == 1:
                frame = bytes([0x81, len(payload)]) + payload
                self.request.sendall(frame)


class _WebSocketEchoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def test_observer_captura_frames_websocket_reais_via_chromium():
    from playwright.sync_api import sync_playwright
    from app.adapters.edge.portas_observabilidade import BrowserTrafficObserver

    server = _WebSocketEchoServer(("127.0.0.1", 0), _WebSocketEchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ws_url = f"ws://127.0.0.1:{server.server_address[1]}/echo"
    observer = BrowserTrafficObserver()
    started = observer.start(cdp_url=CDP_URL)
    assert started["success"] is True
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(CDP_URL)
            page = browser.contexts[0].new_page()
            try:
                page.goto(PAGE_URL)
                echoed = page.evaluate(
                    """url => new Promise((resolve, reject) => {
                        const ws = new WebSocket(url);
                        const timer = setTimeout(() => reject(new Error("websocket timeout")), 8000);
                        ws.onopen = () => ws.send("jarvis-ws-probe");
                        ws.onmessage = event => {
                            clearTimeout(timer);
                            ws.close();
                            resolve(event.data);
                        };
                        ws.onerror = () => reject(new Error("websocket error"));
                    })""",
                    ws_url,
                )
                assert echoed == "jarvis-ws-probe"
                events = observer.events(limit=100)["events"]
                assert any(event["type"] == "websocket_open" and event.get("host") == "127.0.0.1" for event in events)
                frames = [event for event in events if event["type"] == "websocket_frame"]
                assert any(event["direction"] == "sent" for event in frames)
                assert any(event["direction"] == "received" for event in frames)
            finally:
                page.close()
    finally:
        observer.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

[executed on device: DESKTOP-HPJ82UA (d504f4a4-8a27-4cc9-94f5-7abc9b926b55)]