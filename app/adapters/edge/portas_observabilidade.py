# -*- coding: utf-8 -*-
"""Observabilidade de tráfego HTTP(S) e WebSocket no Chromium via CDP.

Captura eventos em memória, com buffer limitado. Não persiste cookies, headers de
autenticação, corpos HTTP ou payloads WebSocket por padrão.
"""
from __future__ import annotations

import asyncio
import json
import re
import threading
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
        # Binary payloads remain metadata-only even with text preview enabled.
        return {"kind": "binary", "bytes": len(payload)}

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
    """Observador persistente; Playwright roda em loop asyncio dedicado."""

    def __init__(self, max_events: int = 2000) -> None:
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._next_id = 1
        self._next_request_id = 1
        self._request_ids: dict[int, int] = {}
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: list[Any] = []
        self._attached_pages: set[int] = set()
        self._active = False
        self._capture_payloads = False
        self._started_at: str | None = None
        self._cdp_url = CDP_URL
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._startup_event: threading.Event | None = None
        self._startup_error: str | None = None

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

    @staticmethod
    def _request_key(request: Any) -> int:
        # Playwright may create a fresh Python wrapper for response.request;
        # the underlying implementation object remains stable across wrappers.
        return id(getattr(request, "_impl_obj", request))

    def _on_request(self, request: Any) -> None:
        url, host = sanitizar_url(request.url)
        with self._lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            self._request_ids[self._request_key(request)] = request_id
            capture_payloads = self._capture_payloads
        fields: dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "url": url,
            "host": host,
            "resource_type": request.resource_type,
        }
        if capture_payloads:
            try:
                post_data = request.post_data
                if post_data is not None:
                    fields["request_payload"] = sanitizar_payload(post_data, True)
            except Exception:
                fields["request_payload"] = {"unavailable": True}
            try:
                headers = request.headers
                safe_names = {"content-type", "accept", "x-requested-with"}
                fields["safe_headers"] = {
                    key.lower(): value for key, value in headers.items() if key.lower() in safe_names
                }
            except Exception:
                fields["safe_headers"] = {}
        self._emit("http_request", **fields)

    def _on_response(self, response: Any) -> None:
        url, host = sanitizar_url(response.url)
        with self._lock:
            request_id = self._request_ids.pop(self._request_key(response.request), None)
        try:
            content_type = response.headers.get("content-type")
        except Exception:
            content_type = None
        self._emit(
            "http_response",
            request_id=request_id,
            url=url,
            host=host,
            status=response.status,
            status_text=response.status_text,
            content_type=content_type,
        )

    def _on_request_failed(self, request: Any) -> None:
        url, host = sanitizar_url(request.url)
        with self._lock:
            request_id = self._request_ids.pop(self._request_key(request), None)
        self._emit(
            "http_request_failed",
            request_id=request_id,
            method=request.method,
            url=url,
            host=host,
            failure=request.failure,
        )

    def _on_websocket(self, websocket: Any) -> None:
        url, host = sanitizar_url(websocket.url)
        self._emit("websocket_open", url=url, host=host)
        websocket.on("framesent", lambda payload: self._on_websocket_frame("sent", websocket, payload))
        websocket.on("framereceived", lambda payload: self._on_websocket_frame("received", websocket, payload))
        websocket.on("close", lambda: self._emit("websocket_close", url=url, host=host))
        websocket.on("socketerror", lambda error: self._emit("websocket_error", url=url, host=host, error=str(error)[:256]))

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

    async def _connect(self, cdp_url: str) -> None:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
        self._contexts = list(self._browser.contexts)
        if not self._contexts:
            raise RuntimeError("CDP conectado, mas nenhum BrowserContext está disponível.")
        for context in self._contexts:
            context.on("request", self._on_request)
            context.on("response", self._on_response)
            context.on("requestfailed", self._on_request_failed)
            context.on("page", self._attach_page)
            for page in context.pages:
                self._attach_page(page)
        with self._lock:
            self._active = True
            self._started_at = datetime.now(timezone.utc).isoformat()

    async def _shutdown(self) -> None:
        playwright = self._playwright
        self._playwright = None
        self._browser = None
        self._contexts = []
        with self._lock:
            self._active = False
            self._attached_pages.clear()
        if playwright is not None:
            await playwright.stop()

    def _run_loop(self, cdp_url: str) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._connect(cdp_url))
        except Exception as exc:
            self._startup_error = f"{type(exc).__name__}: {exc}"
            try:
                loop.run_until_complete(self._shutdown())
            except Exception:
                pass
            if self._startup_event is not None:
                self._startup_event.set()
            loop.close()
            return
        if self._startup_event is not None:
            self._startup_event.set()
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._shutdown())
            except Exception:
                pass
            loop.close()

    def start(self, *, cdp_url: str = CDP_URL, capture_payloads: bool = False, max_events: int = 2000) -> dict[str, Any]:
        with self._lock:
            if self._active:
                return self.status()
            self._capture_payloads = bool(capture_payloads)
            self._events = deque(maxlen=max(100, min(int(max_events), 10000)))
            self._next_id = 1
            self._cdp_url = cdp_url
            self._startup_error = None
            self._startup_event = threading.Event()
            startup_event = self._startup_event
            self._thread = threading.Thread(target=self._run_loop, args=(cdp_url,), name="jarvis-browser-traffic", daemon=True)
            thread = self._thread
            thread.start()

        if not startup_event.wait(timeout=20):
            return {"success": False, "error": "Timeout conectando ao Chromium via CDP (20s)."}
        if self._startup_error:
            return {"success": False, "error": self._startup_error}
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._active:
                return {"success": True, "active": False, "events_buffered": len(self._events)}
            loop = self._loop
            thread = self._thread
        if loop is None or thread is None:
            return {"success": False, "error": "loop de observabilidade indisponível"}
        try:
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
            future.result(timeout=10)
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=10)
        except Exception as exc:
            return {"success": False, "active": self._active, "error": f"{type(exc).__name__}: {exc}"}
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
