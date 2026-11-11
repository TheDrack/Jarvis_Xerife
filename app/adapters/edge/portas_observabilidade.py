# -*- coding: utf-8 -*-
"""Observabilidade HTTP(S), WebSocket e captura binária de mídia via CDP.

A captura de mídia é opt-in, em memória e limitada. URLs são sanitizadas;
nenhum cookie, header de autenticação ou credencial é armazenado. O mecanismo
captura bytes entregues pelo Chromium, mas não descriptografa nem contorna DRM.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.adapters.edge import portas_core


_REDACT_KEYS = re.compile(r"(pass(word)?|token|secret|auth|cookie|api.?key|credential|session)", re.I)
_REDACT_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*")
_REDACT_ASSIGNMENT = re.compile(
    r"(?i)((?:token|secret|password|passwd|authorization|api[_-]?key|cookie)\s*[:=]\s*)[^\s,;&]+"
)
_MEDIA_MIME_PREFIXES = ("audio/", "video/")
_MEDIA_MIME_TYPES = {
    "application/dash+xml",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/vnd.yt-ump",
}
_MEDIA_CHUNK_BYTES = 256 * 1024
_MEDIA_CHUNK_BUFFER_SIZE = 128
_MEDIA_STREAM_LIMIT = 64


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
        self._request_started_at: dict[int, float] = {}
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: list[Any] = []
        self._attached_pages: set[int] = set()
        self._active = False
        self._capture_payloads = False
        self._capture_media = False
        self._media_sessions: dict[int, Any] = {}
        self._media_request_streams: dict[tuple[int, str], str] = {}
        self._media_streams: dict[str, dict[str, Any]] = {}
        self._media_sequences: dict[str, int] = {}
        self._media_offsets: dict[str, int] = {}
        self._media_chunks: deque[dict[str, Any]] = deque(maxlen=_MEDIA_CHUNK_BUFFER_SIZE)
        self._started_at: str | None = None
        self._cdp_url = portas_core.CDP_URL
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

    @staticmethod
    def _is_media_response(response: dict[str, Any]) -> bool:
        """Classifica respostas de mídia sem depender do domínio/provedor."""
        mime = str(response.get("mimeType") or "").split(";", 1)[0].strip().lower()
        if mime.startswith(_MEDIA_MIME_PREFIXES) or mime in _MEDIA_MIME_TYPES:
            return True
        headers = response.get("headers") or {}
        if isinstance(headers, dict):
            content_type = next(
                (str(value) for key, value in headers.items() if str(key).lower() == "content-type"),
                "",
            ).split(";", 1)[0].strip().lower()
            if content_type.startswith(_MEDIA_MIME_PREFIXES) or content_type in _MEDIA_MIME_TYPES:
                return True
        # Some streaming endpoints report application/octet-stream while the
        # URL carries a declared media MIME (e.g. YouTube's mime=audio/mp4).
        try:
            query = dict(parse_qsl(urlsplit(str(response.get("url") or "")).query, keep_blank_values=True))
        except ValueError:
            query = {}
        declared = str(query.get("mime") or "").split(";", 1)[0].strip().lower()
        return declared.startswith(_MEDIA_MIME_PREFIXES) or declared in _MEDIA_MIME_TYPES

    def _store_media_bytes(self, stream_id: str, payload: bytes, timestamp: float | None = None) -> int:
        """Armazena bytes sem transformação, em chunks base64 com orçamento global fixo."""
        if not isinstance(payload, bytes) or not payload:
            return 0
        if stream_id not in self._media_streams:
            return 0
        captured = 0
        stamp = timestamp if timestamp is not None else time.monotonic()
        with self._lock:
            for offset in range(0, len(payload), _MEDIA_CHUNK_BYTES):
                chunk = payload[offset:offset + _MEDIA_CHUNK_BYTES]
                sequence = self._media_sequences.get(stream_id, 0) + 1
                stream_offset = self._media_offsets.get(stream_id, 0)
                self._media_sequences[stream_id] = sequence
                self._media_offsets[stream_id] = stream_offset + len(chunk)
                self._media_chunks.append({
                    "stream_id": stream_id,
                    "sequence": sequence,
                    "offset": stream_offset,
                    "timestamp": stamp,
                    "bytes": len(chunk),
                    "data": base64.b64encode(chunk).decode("ascii"),
                })
                captured += len(chunk)
            stream = self._media_streams[stream_id]
            stream["bytes_received"] = self._media_offsets[stream_id]
            stream["chunks_received"] = self._media_sequences[stream_id]
        return captured

    def media_chunks(self, stream_id: str, *, after_sequence: int = 0, limit: int = 16) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 32))
        cursor = max(0, int(after_sequence))
        with self._lock:
            stream = self._media_streams.get(str(stream_id))
            if stream is None:
                return {"success": False, "error": "stream_not_found", "stream_id": str(stream_id)}
            available = [
                item for item in self._media_chunks
                if item["stream_id"] == stream_id
            ]
            first_available = available[0]["sequence"] if available else self._media_sequences.get(stream_id, 0) + 1
            selected = [item for item in available if item["sequence"] > cursor][:bounded_limit]
            next_sequence = selected[-1]["sequence"] if selected else cursor
            return {
                "success": True,
                "stream_id": stream_id,
                "mime_type": stream.get("mime_type"),
                "protocol": stream.get("protocol"),
                "status": stream.get("status"),
                "count": len(selected),
                "chunks": [dict(item) for item in selected],
                "first_available_sequence": first_available,
                "next_after_sequence": next_sequence,
                "gap": cursor < first_available - 1,
            }

    def media_events(self, *, limit: int = 50) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 100))
        with self._lock:
            streams = list(self._media_streams.values())[-bounded_limit:]
            return {
                "success": True,
                "capture_enabled": self._capture_media,
                "streams": [dict(item) for item in streams],
                "count": len(streams),
                "buffered_chunks": len(self._media_chunks),
            }

    def _on_request(self, request: Any) -> None:
        url, host = sanitizar_url(request.url)
        with self._lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            request_key = self._request_key(request)
            self._request_ids[request_key] = request_id
            self._request_started_at[request_key] = time.monotonic()
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
            request_id = self._request_ids.get(self._request_key(response.request))
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

    def _on_request_finished(self, request: Any) -> None:
        url, host = sanitizar_url(request.url)
        request_key = self._request_key(request)
        with self._lock:
            request_id = self._request_ids.pop(request_key, None)
            started_at = self._request_started_at.pop(request_key, None)
        duration_ms = round((time.monotonic() - started_at) * 1000, 2) if started_at is not None else None
        self._emit(
            "http_request_finished",
            request_id=request_id,
            method=request.method,
            url=url,
            host=host,
            duration_ms=duration_ms,
        )

    def _on_request_failed(self, request: Any) -> None:
        url, host = sanitizar_url(request.url)
        request_key = self._request_key(request)
        with self._lock:
            request_id = self._request_ids.pop(request_key, None)
            self._request_started_at.pop(request_key, None)
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

    def _on_media_data_received(self, session: Any, params: dict[str, Any]) -> None:
        request_id = str(params.get("requestId") or "")
        with self._lock:
            stream_id = self._media_request_streams.get((id(session), request_id))
        encoded = params.get("data")
        if not stream_id or not isinstance(encoded, str) or not encoded:
            return
        try:
            payload = base64.b64decode(encoded, validate=False)
        except (ValueError, TypeError):
            self._emit("media_stream_error", stream_id=stream_id, error="invalid_base64_chunk")
            return
        self._store_media_bytes(stream_id, payload, params.get("timestamp"))

    def _on_media_loading_finished(self, session: Any, params: dict[str, Any]) -> None:
        request_id = str(params.get("requestId") or "")
        with self._lock:
            stream_id = self._media_request_streams.pop((id(session), request_id), None)
            stream = self._media_streams.get(stream_id) if stream_id else None
            if stream is not None:
                stream["status"] = "finished"
                stream["finished_at"] = datetime.now(timezone.utc).isoformat()
        if stream_id:
            self._emit("media_stream_finished", stream_id=stream_id)

    def _on_media_loading_failed(self, session: Any, params: dict[str, Any]) -> None:
        request_id = str(params.get("requestId") or "")
        with self._lock:
            stream_id = self._media_request_streams.pop((id(session), request_id), None)
            stream = self._media_streams.get(stream_id) if stream_id else None
            if stream is not None:
                stream["status"] = "failed"
                stream["error"] = str(params.get("errorText") or "loading_failed")[:160]
        if stream_id:
            self._emit("media_stream_failed", stream_id=stream_id)

    async def _start_media_stream(self, session: Any, params: dict[str, Any]) -> None:
        response = params.get("response") or {}
        if not self._is_media_response(response):
            return
        request_id = str(params.get("requestId") or "")
        if not request_id:
            return
        url, host = sanitizar_url(str(response.get("url") or ""))
        mime_type = str(response.get("mimeType") or "")
        headers = response.get("headers") or {}
        if not mime_type and isinstance(headers, dict):
            mime_type = next(
                (str(value) for key, value in headers.items() if str(key).lower() == "content-type"),
                "",
            )
        stream_id = uuid.uuid4().hex
        lowered_mime = mime_type.split(";", 1)[0].strip().lower()
        protocol = "ump" if lowered_mime == "application/vnd.yt-ump" else (
            "hls" if "mpegurl" in lowered_mime else "dash" if "dash+xml" in lowered_mime else "media"
        )
        stream = {
            "stream_id": stream_id,
            "request_id": request_id,
            "url": url,
            "host": host,
            "mime_type": mime_type[:128],
            "protocol": protocol,
            "status": "streaming",
            "http_status": response.get("status"),
            "bytes_received": 0,
            "chunks_received": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._media_streams[stream_id] = stream
            self._media_request_streams[(id(session), request_id)] = stream_id
            self._media_sequences[stream_id] = 0
            self._media_offsets[stream_id] = 0
            while len(self._media_streams) > _MEDIA_STREAM_LIMIT:
                oldest_id = next(iter(self._media_streams))
                self._media_streams.pop(oldest_id, None)
                self._media_sequences.pop(oldest_id, None)
                self._media_offsets.pop(oldest_id, None)
        self._emit(
            "media_stream_started",
            stream_id=stream_id,
            url=url,
            host=host,
            mime_type=mime_type[:128],
            protocol=protocol,
            http_status=response.get("status"),
        )
        try:
            result = await session.send("Network.streamResourceContent", {"requestId": request_id})
            buffered = result.get("bufferedData") if isinstance(result, dict) else None
            if isinstance(buffered, str) and buffered:
                self._store_media_bytes(stream_id, base64.b64decode(buffered, validate=False))
        except Exception as exc:
            with self._lock:
                current = self._media_streams.get(stream_id)
                if current is not None:
                    current["status"] = "unavailable"
                    current["error"] = type(exc).__name__
                self._media_request_streams.pop((id(session), request_id), None)
            self._emit("media_stream_unavailable", stream_id=stream_id, error=type(exc).__name__)

    async def _attach_media_page(self, page: Any) -> None:
        if not self._capture_media:
            return
        marker = id(page)
        with self._lock:
            if marker in self._media_sessions:
                return
        session = None
        try:
            session = await page.context.new_cdp_session(page)
            await session.send("Network.enable")
            session.on(
                "Network.responseReceived",
                lambda params: asyncio.create_task(self._start_media_stream(session, params)),
            )
            session.on("Network.dataReceived", lambda params: self._on_media_data_received(session, params))
            session.on("Network.loadingFinished", lambda params: self._on_media_loading_finished(session, params))
            session.on("Network.loadingFailed", lambda params: self._on_media_loading_failed(session, params))
            with self._lock:
                self._media_sessions[marker] = session
        except Exception as exc:
            if session is not None:
                try:
                    await session.detach()
                except Exception:
                    pass
            self._emit("media_capture_page_error", error=type(exc).__name__)

    def _attach_page(self, page: Any) -> None:
        marker = id(page)
        with self._lock:
            if marker in self._attached_pages:
                return
            self._attached_pages.add(marker)
        page.on("websocket", self._on_websocket)
        if self._capture_media:
            asyncio.create_task(self._attach_media_page(page))

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
            context.on("requestfinished", self._on_request_finished)
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
            media_sessions = list(self._media_sessions.values())
            self._media_sessions.clear()
            self._active = False
            self._attached_pages.clear()
            self._media_request_streams.clear()
        for session in media_sessions:
            try:
                await session.detach()
            except Exception:
                pass
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

    def start(
        self,
        *,
        cdp_url: str | None = None,
        capture_payloads: bool = False,
        capture_media: bool = False,
        max_events: int = 2000,
    ) -> dict[str, Any]:
        with self._lock:
            if self._active:
                if capture_media and not self._capture_media:
                    return {
                        "success": False,
                        "error": "Observador já ativo sem captura de mídia; pare e reinicie com capturar_midia=True.",
                    }
                return self.status()
            self._capture_payloads = bool(capture_payloads)
            self._capture_media = bool(capture_media)
            self._events = deque(maxlen=max(100, min(int(max_events), 10000)))
            self._next_id = 1
            self._media_streams.clear()
            self._media_sequences.clear()
            self._media_offsets.clear()
            self._media_chunks.clear()
            self._media_request_streams.clear()
            cdp_url = cdp_url or portas_core.CDP_URL
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
                "media_capture": self._capture_media,
                "media_sessions": len(self._media_sessions),
                "media_streams": len(self._media_streams),
                "media_chunks_buffered": len(self._media_chunks),
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
            self._media_chunks.clear()
            return {"success": True, "cleared": removed, "media_chunks_cleared": True}


observer = BrowserTrafficObserver()


def registrar_observabilidade_portas(mcp: Any, tracked_action: Any) -> None:
    """Registra as ferramentas de controle, consulta e captura de mídia."""

    @mcp.tool()
    @tracked_action("Configurando endpoint CDP do Chromium")
    def portas_cdp_configurar(url: str) -> dict[str, Any]:
        """Define endpoint CDP local (localhost); aceita ws:// dinâmico do agent-browser."""
        return portas_core.configurar_cdp_url(url)

    @mcp.tool()
    @tracked_action("Descobrindo endpoint CDP do agent-browser")
    def portas_cdp_descobrir_agent_browser(session: str = "default") -> dict[str, Any]:
        """Obtém o endpoint CDP de uma sessão agent-browser e configura o núcleo."""
        import shutil
        import subprocess

        executable = shutil.which("agent-browser")
        if not executable:
            return {"success": False, "error": "agent-browser não está no PATH do processo MCP."}
        if not session or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", session):
            return {"success": False, "error": "Nome de sessão inválido."}
        try:
            completed = subprocess.run(
                [executable, "--session", session, "get", "cdp-url"],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
        match = re.search(r"wss?://127\.0\.0\.1:\d+/[^\s]+|https?://(?:127\.0\.0\.1|localhost):\d+", completed.stdout)
        if completed.returncode != 0 or not match:
            return {
                "success": False,
                "error": "Não foi possível obter endpoint CDP local.",
                "detail": completed.stderr[-500:],
            }
        configured = portas_core.configurar_cdp_url(match.group(0))
        return {**configured, "session": session, "source": "agent-browser"}

    @mcp.tool()
    @tracked_action("Iniciando observabilidade do navegador")
    def portas_trafego_iniciar(
        capturar_payloads: bool = False,
        limite_eventos: int = 2000,
        capturar_midia: bool = False,
    ) -> dict[str, Any]:
        """Observa HTTP(S)/WebSocket; capturar_midia habilita chunks binários via CDP."""
        return observer.start(
            capture_payloads=capturar_payloads,
            capture_media=capturar_midia,
            max_events=limite_eventos,
        )

    @mcp.tool()
    @tracked_action("Consultando fluxos de mídia")
    def portas_media_eventos(limit: int = 50) -> dict[str, Any]:
        """Lista fluxos de mídia descobertos e seus metadados, sem devolver bytes."""
        return observer.media_events(limit=limit)

    @mcp.tool()
    @tracked_action("Lendo chunks binários de mídia")
    def portas_media_chunks(stream_id: str, after_sequence: int = 0, limit: int = 16) -> dict[str, Any]:
        """Retorna chunks base64 ordenados para consumidores autorizados; buffer limitado."""
        return observer.media_chunks(stream_id, after_sequence=after_sequence, limit=limit)

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
        """Retorna estado da captura, número de abas ligadas e tamanho dos buffers."""
        return observer.status()

    @mcp.tool()
    @tracked_action("Limpando eventos de tráfego")
    def portas_trafego_limpar() -> dict[str, Any]:
        """Limpa buffers em memória sem interromper a captura."""
        return observer.clear()
