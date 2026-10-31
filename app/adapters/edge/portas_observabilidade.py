# -*- coding: utf-8 -*-
"""Observabilidade de tráfego HTTP(S) e WebSocket no Chromium via CDP.

Captura eventos em memória, com buffer limitado. Não persiste cookies, headers de
autenticação, corpos HTTP ou payloads WebSocket por padrão.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.adapters.edge.portas_core import CDP_URL


_REDACT_KEYS = re.compile(r"(pass(word)?|token|secret|auth|cookie|api.?key|credential|session)", re.I)
_REDACT_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*")
_REDACT_ASSIGNMENT = re.compile(
    r"(?i)((?:token|secret|password|passwd|authorization|api[_-]?key|cookie)\s*[:=]\s*)[^\s,;&]+"
)


def sanitizar_url(url: str) -> tuple[str, str]:
    """Remove credenciais e valores de query; preserva host, caminho e nomes dos parâmetros."""
    try:
        parsed = urlsplit(str(url))
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        query = urlencode([(key, "[REDACTED]") for key, _ in parse_qsl(parsed.query, keep_blank_values=True)])
        safe = urlunsplit((parsed.scheme, host, parsed.path, query, ""))
        return safe, parsed.hostname or ""
    except (TypeError, ValueError):
        return "<invalid-url>", ""


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _REDACT_KEYS.search(str(key)) else _redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def sanitizar_payload(payload: str | bytes, enabled: bool) -> dict[str, Any]:
    """Retorna metadados por padrão; com opt-in, devolve preview limitado e redigido."""
    if isinstance(payload, bytes):
        result: dict[str, Any] = {"kind": "binary", "bytes": len(payload)}
        if enabled:
            result["preview_hex"] = payload[:128].hex()
            result["truncated"] = len(payload) > 128
        return result

    raw = str(payload)
    result = {"kind": "text", "characters": len(raw)}
    if enabled:
        try:
            parsed = json.loads(raw)
            preview = json.dumps(_redact_json(parsed), ensure_ascii=False, separators=(",", ":"))
        except (json.JSONDecodeError, TypeError):
            preview = _REDACT_BEARER.sub(r"\1[REDACTED]", raw)
            preview = _REDACT_ASSIGNMENT.sub(r"\1[REDACTED]", preview)
        result["preview"] = preview[:512]
        result["truncated"] = len(preview) > 512
    return result


class BrowserTrafficObserver:
    """Observador singleton para todas as abas dos contextos ligados via CDP."""

    def __init__(self, max_events: int = 2000) -> None:
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._next_id = 1
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: list[Any] = []
        self._attached_pages: set[int] = set()
        self._active = False
        self._capture_payloads = False
        self._started_at: str | None = None
        self._cdp_url = CDP_URL

    def _emit(self, event_type: str, **fields: Any) -> None:
        with self._lock:
            event = {
                "id": self._next_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": event_type,
                **fields,
            }
            self._next_id += 1
            self._events.append(event)

    def _on_request(self, request: Any) -> None:
        url, host = sanitizar_url(request.url)
        self._emit(
            "http_request",
            method=request.method,
            url=url,
            host=host,
            resource_type=request.resource_type,
        )

    def _on_response(self, response: Any) -> None:
        url, host = sanitizar_url(response.url)
        self._emit(
            "http_response",
            url=url,
            host=host,
            status=response.status,
            status_text=response.status_text,
        )

    def _on_request_failed(self, request: Any) -> None:
        url, host = sanitizar_url(request.url)
        self._emit(
            "http_request_failed",
            method=request.method,
            url=url,
            host=host,
            failure=request.failure,
        )

    def _on_websocket(self, websocket: Any) -> None:
        url, host = sanitizar_url(websocket.url)
        self._emit("websocket_open", url=url, host=host)
        websocket.on(
            "framesent",
            lambda payload: self._on_websocket_frame("sent", websocket, payload),
        )
        websocket.on(
            "framereceived",
            lambda payload: self._on_websocket_frame("received", websocket, payload),
        )
        websocket.on("close", lambda: self._emit("websocket_close", url=url, host=host))
        websocket.on(
            "socketerror",
            lambda error: self._emit("websocket_error", url=url, host=host, error=str(error)[:256]),
        )

    def _on_websocket_frame(self, direction: str, websocket: Any, payload: str | bytes) -> None:
        url, host = sanitizar_url(websocket.url)
        self._emit(
            "websocket_frame",
            direction=direction,
            url=url,
            host=host,
            payload=sanitizar_payload(payload, self._capture_payloads),
        )

    def _attach_page(self, page: Any) -> None:
        marker = id(page)
        with self._lock:
            if marker in self._attached_pages:
                return
            self._attached_pages.add(marker)
        page.on("websocket", self._on_websocket)

    def start(self, *, cdp_url: str = CDP_URL, capture_payloads: bool = False, max_events: int = 2000) -> dict[str, Any]:
        with self._lock:
            if self._active:
                return self.status()
            self._capture_payloads = bool(capture_payloads)
            self._events = deque(maxlen=max(100, min(int(max_events), 10000)))
            self._next_id = 1
            self._cdp_url = cdp_url

        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            contexts = list(browser.contexts)
            if not contexts:
                playwright.stop()
                return {"success": False, "error": "CDP conectado, mas nenhum BrowserContext está disponível."}

            for context in contexts:
                context.on("request", self._on_request)
                context.on("response", self._on_response)
                context.on("requestfailed", self._on_request_failed)
                context.on("page", self._attach_page)
                for page in context.pages:
                    self._attach_page(page)

            with self._lock:
                self._playwright = playwright
                self._browser = browser
                self._contexts = contexts
                self._active = True
                self._started_at = datetime.now(timezone.utc).isoformat()
            return self.status()
        except Exception as exc:
            try:
                if "playwright" in locals():
                    playwright.stop()
            except Exception:
                pass
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return {"success": True, "active": False, "events_buffered": len(self._events)}
            playwright = self._playwright
            self._active = False
            self._playwright = None
            self._browser = None
            self._contexts = []
            self._attached_pages.clear()
        try:
            if playwright is not None:
                playwright.stop()
        except Exception as exc:
            return {"success": False, "active": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"success": True, "active": False, "events_buffered": len(self._events)}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "success": True,
                "active": self._active,
                "started_at": self._started_at,
                "cdp_url": self._cdp_url,
                "contexts": len(self._contexts),
                "tabs_attached": len(self._attached_pages),
                "events_buffered": len(self._events),
                "payload_capture": self._capture_payloads,
            }

    def events(self, *, limit: int = 100, after_id: int = 0, host_contains: str = "") -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 500))
        needle = host_contains.casefold().strip()
        with self._lock:
            selected = [
                event for event in self._events
                if event["id"] > max(0, int(after_id))
                and (not needle or needle in str(event.get("host", "")).casefold())
            ]
            return {
                "success": True,
                "active": self._active,
                "count": len(selected[-bounded_limit:]),
                "events": selected[-bounded_limit:],
                "next_after_id": selected[-1]["id"] if selected else max(0, int(after_id)),
            }

    def clear(self) -> dict[str, Any]:
        with self._lock:
            removed = len(self._events)
            self._events.clear()
            return {"success": True, "cleared": removed}


observer = BrowserTrafficObserver()


def registrar_observabilidade_portas(mcp: Any, tracked_action: Any) -> None:
    """Registra as ferramentas de controle e consulta do observador."""

    @mcp.tool()
    @tracked_action("Iniciando observabilidade do navegador")
    def portas_trafego_iniciar(capturar_payloads: bool = False, limite_eventos: int = 2000) -> dict[str, Any]:
        """Começa a observar HTTP(S) e frames WebSocket em todas as abas CDP abertas.

        Por padrão, payloads não são armazenados; capturar_payloads=True habilita
        previews limitados com redação de campos sensíveis.
        """
        return observer.start(capture_payloads=capturar_payloads, max_events=limite_eventos)

    @mcp.tool()
    @tracked_action("Parando observabilidade do navegador")
    def portas_trafego_parar() -> dict[str, Any]:
        """Para a captura e desconecta o observador sem fechar o Chromium."""
        return observer.stop()

    @mcp.tool()
    @tracked_action("Consultando tráfego do navegador")
    def portas_trafego_eventos(limit: int = 100, after_id: int = 0, host_contains: str = "") -> dict[str, Any]:
        """Consulta eventos recentes, com paginação incremental e filtro opcional por host."""
        return observer.events(limit=limit, after_id=after_id, host_contains=host_contains)

    @mcp.tool()
    @tracked_action("Consultando estado da observabilidade")
    def portas_trafego_status() -> dict[str, Any]:
        """Retorna estado da captura, número de abas ligadas e tamanho do buffer."""
        return observer.status()

    @mcp.tool()
    @tracked_action("Limpando eventos de tráfego")
    def portas_trafego_limpar() -> dict[str, Any]:
        """Limpa o buffer em memória sem interromper a captura."""
        return observer.clear()
