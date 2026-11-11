# -*- coding: utf-8 -*-
"""Motor de captura de mídia em tempo real para o observador de tráfego.

Complementa ``BrowserTrafficObserver`` sem substituí-lo: o observador continua
leve (metadados + redação). Este módulo adiciona uma camada independente que
armazena bytes binários de respostas/streams quando habilitado, com limites de
memória, backpressure e timestamps, e expõe adaptadores pluggáveis para UMP,
HLS e DASH.

Não decodifica áudio/vídeo (requer ffmpeg/pyav); entrega bytes brutos e
metadados para consumidores (player desktop, stream IA).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

import re

_MEDIA_URL_HINTS = re.compile(
    r"(videoplayback|\.m3u8|\.mpd|\.ts(?:\?|$)|\.m4s(?:\?|$)|/media/|/stream/)",
    re.I,
)
_MEDIA_CONTENT_TYPES = re.compile(
    r"(video/|audio/|application/(vnd\.apple\.mpegurl|dash\+xml|x-mpegurl)|octet-stream)",
    re.I,
)


def is_media_request(url: str, content_type: str | None = None) -> bool:
    """Heurística para decidir se uma resposta merece captura binária."""
    try:
        path = urlsplit(str(url)).path
    except Exception:
        path = str(url)
    if _MEDIA_URL_HINTS.search(str(url)):
        return True
    if content_type and _MEDIA_CONTENT_TYPES.search(str(content_type)):
        return True
    return False


@dataclass
class MediaChunk:
    stream_id: str
    sequence: int
    timestamp: float
    data: bytes
    direction: str = "response"  # response | websocket


@dataclass
class MediaStream:
    stream_id: str
    url: str
    host: str
    content_type: str | None
    adapter: str = "raw"  # raw | ump | hls | dash
    started_at: float = field(default_factory=time.monotonic)
    total_bytes: int = 0
    chunks: deque[MediaChunk] = field(default_factory=lambda: deque(maxlen=1024))
    ump_parts: list = field(default_factory=list)
    truncated: bool = False
    closed: bool = False
    last_activity: float = field(default_factory=time.monotonic)

    def to_status(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "url": self.url,
            "host": self.host,
            "content_type": self.content_type,
            "adapter": self.adapter,
            "chunks": len(self.chunks),
            "ump_parts": len(self.ump_parts),
            "total_bytes": self.total_bytes,
            "truncated": self.truncated,
            "closed": self.closed,
            "last_activity": self.last_activity,
        }


class MediaCaptureEngine:
    """Armazena bytes de mídia com limites de memória e backpressure."""

    def __init__(
        self,
        *,
        max_streams: int = 32,
        max_bytes_per_stream: int = 16 * 1024 * 1024,
        max_total_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self._lock = threading.RLock()
        self._streams: OrderedDict[str, MediaStream] = OrderedDict()
        self._max_streams = max(1, int(max_streams))
        self._max_bytes_per_stream = max(1024, int(max_bytes_per_stream))
        self._max_total_bytes = max(1024, int(max_total_bytes))
        self._total_bytes = 0
        self._next_stream = 1
        self._next_chunk: dict[str, int] = {}
        self._adapters: dict[str, Callable[[MediaStream, bytes], None]] = {}
        self._enabled = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def enable(self) -> None:
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def register_adapter(self, name: str, handler: Callable[[MediaStream, bytes], None]) -> None:
        with self._lock:
            self._adapters[name] = handler

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #
    def _evict_if_needed(self) -> None:
        # Evict oldest streams until within limits (caller holds lock).
        while len(self._streams) > self._max_streams or self._total_bytes > self._max_total_bytes:
            if not self._streams:
                break
            sid, stream = next(iter(self._streams.items()))
            self._streams.pop(sid, None)
            self._total_bytes = max(0, self._total_bytes - stream.total_bytes)
            stream.chunks.clear()

    def open_stream(
        self,
        url: str,
        host: str = "",
        content_type: str | None = None,
        adapter: str = "raw",
    ) -> str | None:
        if not self._enabled:
            return None
        with self._lock:
            self._evict_if_needed()
            sid = f"media-{self._next_stream}"
            self._next_stream += 1
            self._next_chunk[sid] = 0
            stream = MediaStream(
                stream_id=sid,
                url=url,
                host=host,
                content_type=content_type,
                adapter=adapter,
            )
            self._streams[sid] = stream
            return sid

    def append(
        self,
        stream_id: str | None,
        data: bytes,
        *,
        direction: str = "response",
        adapter_hint: str | None = None,
    ) -> bool:
        if not self._enabled or not data or stream_id is None:
            return False
        with self._lock:
            stream = self._streams.get(stream_id)
            if stream is None or stream.closed:
                return False
            if stream.total_bytes + len(data) > self._max_bytes_per_stream:
                stream.truncated = True
                stream.closed = True
                return False
            seq = self._next_chunk.get(stream_id, 0)
            self._next_chunk[stream_id] = seq + 1
            chunk = MediaChunk(
                stream_id=stream_id,
                sequence=seq,
                timestamp=time.time(),
                data=bytes(data),
                direction=direction,
            )
            stream.chunks.append(chunk)
            stream.total_bytes += len(data)
            stream.last_activity = time.monotonic()
            self._total_bytes += len(data)
            if adapter_hint and adapter_hint in self._adapters:
                try:
                    self._adapters[adapter_hint](stream, data)
                except Exception:
                    pass
            self._evict_if_needed()
            return True

    def close_stream(self, stream_id: str) -> None:
        with self._lock:
            stream = self._streams.get(stream_id)
            if stream is not None:
                stream.closed = True

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #
    def streams(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_status() for s in self._streams.values()]

    def get(self, stream_id: str) -> MediaStream | None:
        with self._lock:
            return self._streams.get(stream_id)

    def chunks(
        self,
        stream_id: str,
        *,
        after_sequence: int = -1,
        limit: int = 64,
    ) -> dict[str, Any]:
        with self._lock:
            stream = self._streams.get(stream_id)
            if stream is None:
                return {"success": False, "error": "stream não encontrado"}
            bounded = max(1, min(int(limit), 512))
            selected = [c for c in stream.chunks if c.sequence > after_sequence]
            return {
                "success": True,
                "stream_id": stream_id,
                "count": len(selected[:bounded]),
                "chunks": [
                    {
                        "sequence": c.sequence,
                        "timestamp": c.timestamp,
                        "bytes": len(c.data),
                        "direction": c.direction,
                    }
                    for c in selected[:bounded]
                ],
                "next_after_sequence": selected[bounded - 1].sequence if len(selected) >= bounded else (selected[-1].sequence if selected else after_sequence),
                "total_bytes": stream.total_bytes,
                "truncated": stream.truncated,
                "closed": stream.closed,
            }

    def ump_parts(self, stream_id: str) -> dict[str, Any]:
        with self._lock:
            stream = self._streams.get(stream_id)
            if stream is None:
                return {"success": False, "error": "stream não encontrado"}
            parts = getattr(stream, "ump_parts", [])
            assembler = getattr(stream, "ump_segments", None)
            completed = getattr(assembler, "completed", []) if assembler else []
            segments = {str(k): len(v) for k, v in getattr(assembler, "segments", {}).items()} if assembler else {}
            return {
                "success": True,
                "stream_id": stream_id,
                "count": len(parts),
                "parts": [{"type": ptype, "name": UMP_PART_NAMES.get(ptype, "UNKNOWN"), "bytes": len(payload)} for ptype, payload in parts],
                "segments": segments,
                "completed_segments": completed,
            }

    def read_bytes(self, stream_id: str, *, max_bytes: int = 65536) -> dict[str, Any]:
        with self._lock:
            stream = self._streams.get(stream_id)
            if stream is None:
                return {"success": False, "error": "stream não encontrado"}
            data = bytearray()
            for c in stream.chunks:
                if len(data) + len(c.data) > max_bytes:
                    break
                data.extend(c.data)
            return {
                "success": True,
                "stream_id": stream_id,
                "bytes": len(data),
                "data_hex": data.hex(),
                "total_bytes": stream.total_bytes,
                "truncated": stream.truncated,
            }

    def clear(self) -> dict[str, Any]:
        with self._lock:
            removed = len(self._streams)
            self._streams.clear()
            self._next_chunk.clear()
            self._total_bytes = 0
            return {"success": True, "removed": removed}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "success": True,
                "enabled": self._enabled,
                "streams": len(self._streams),
                "total_bytes": self._total_bytes,
                "max_streams": self._max_streams,
                "max_bytes_per_stream": self._max_bytes_per_stream,
                "max_total_bytes": self._max_total_bytes,
                "adapters": sorted(self._adapters.keys()),
            }


# --------------------------------------------------------------------------- #
# UMP (Universal Media Protocol) — parser streaming
# --------------------------------------------------------------------------- #

UMP_PART_NAMES = {
    10: "ONESIE_HEADER",
    11: "ONESIE_DATA",
    12: "ONESIE_ENCRYPTED_MEDIA",
    20: "MEDIA_HEADER",
    21: "MEDIA",
    22: "MEDIA_END",
    31: "FORMAT_SELECTION",
    32: "SABR_REDIRECT",
    33: "SABR_ERROR",
    34: "STREAM_PROTECTION_STATUS",
    35: "MEDIA_LIMIT",
    36: "LIVE_METADATA",
    37: "NEXT_REQUEST_POLICY",
    38: "USTREAMER_CONFIG",
}


def _read_ump_varint(buf: bytes, i: int) -> tuple[int, int] | None:
    """Lê um UMP varint. Retorna (valor, bytes_consumidos) ou None se incompleto."""
    if i >= len(buf):
        return None
    first = buf[i]
    if first & 0x80 == 0:
        return first, 1
    if first & 0xC0 == 0x80:
        if i + 1 >= len(buf):
            return None
        return ((first & 0x3F) | (buf[i + 1] << 6)), 2
    if first & 0xE0 == 0xC0:
        if i + 2 >= len(buf):
            return None
        return ((first & 0x1F) | (buf[i + 1] << 5) | (buf[i + 2] << 13)), 3
    if first & 0xF0 == 0xE0:
        if i + 3 >= len(buf):
            return None
        return ((first & 0x0F) | (buf[i + 1] << 4) | (buf[i + 2] << 12) | (buf[i + 3] << 20)), 4
    if first & 0xF8 == 0xF0:
        if i + 4 >= len(buf):
            return None
        # next four bytes little-endian 32-bit; low 3 bits of first ignored
        value = int.from_bytes(buf[i + 1:i + 5], "little")
        return value, 5
    return None


class UmpReader:
    """Parser streaming de envelope UMP. Acumula bytes e emite partes completas."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.parts: list[tuple[int, bytes]] = []
        self.incomplete = False

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self._buf.extend(data)
        emitted: list[tuple[int, bytes]] = []
        i = 0
        n = len(self._buf)
        while i < n:
            t = _read_ump_varint(self._buf, i)
            if t is None:
                self.incomplete = True
                # keep tail
                del self._buf[:i]
                return emitted
            ptype, tc = t
            i += tc
            l = _read_ump_varint(self._buf, i)
            if l is None:
                self.incomplete = True
                del self._buf[:i]
                return emitted
            plen, lc = l
            i += lc
            if i + plen > n:
                self.incomplete = True
                # keep tail starting at the type varint of the incomplete part
                del self._buf[: i - tc - lc]
                return emitted
            payload = bytes(self._buf[i:i + plen])
            i += plen
            emitted.append((ptype, payload))
            self.parts.append((ptype, payload))
        # consumed all
        del self._buf[:i]
        self.incomplete = False
        return emitted

    def reset(self) -> None:
        self._buf.clear()
        self.parts.clear()


class UmpSegmentAssembler:
    """Agrupa partes MEDIA_HEADER/MEDIA/MEDIA_END por header id (heurístico)."""

    def __init__(self) -> None:
        self.segments: dict[int, bytearray] = {}
        self.headers: dict[int, bytes] = {}
        self.completed: list[int] = []

    def _header_id(self, payload: bytes) -> int:
        if not payload:
            return 0
        r = _read_ump_varint(payload, 0)
        if r is None:
            return payload[0]
        return r[0]

    def handle(self, ptype: int, payload: bytes) -> dict[str, Any] | None:
        if ptype == 20:  # MEDIA_HEADER
            hid = self._header_id(payload)
            self.headers[hid] = payload
            self.segments.setdefault(hid, bytearray())
            return {"event": "header", "header_id": hid, "bytes": len(payload)}
        if ptype == 21:  # MEDIA
            hid = self._header_id(payload)
            # strip header id varint from body
            r = _read_ump_varint(payload, 0)
            off = r[1] if r else 0
            body = payload[off:]
            self.segments.setdefault(hid, bytearray()).extend(body)
            return {"event": "media", "header_id": hid, "bytes": len(body)}
        if ptype == 22:  # MEDIA_END
            hid = self._header_id(payload)
            self.completed.append(hid)
            return {"event": "end", "header_id": hid, "total_bytes": len(self.segments.get(hid, b""))}
        return {"event": "part", "type": ptype, "name": UMP_PART_NAMES.get(ptype, "UNKNOWN"), "bytes": len(payload)}


def ump_adapter(stream: MediaStream, data: bytes) -> None:
    """Parseia envelope UMP incrementalmente e armazena partes no stream."""
    reader = getattr(stream, "_ump_reader", None)
    if reader is None:
        reader = UmpReader()
        stream._ump_reader = reader  # type: ignore[attr-defined]
        stream.ump_parts = []  # type: ignore[attr-defined]
        stream.ump_segments = UmpSegmentAssembler()  # type: ignore[attr-defined]
    emitted = reader.feed(data)
    assembler = stream.ump_segments  # type: ignore[attr-defined]
    for ptype, payload in emitted:
        stream.ump_parts.append((ptype, payload))  # type: ignore[attr-defined]
        assembler.handle(ptype, payload)


def hls_adapter(stream: MediaStream, data: bytes) -> None:
    return None


def dash_adapter(stream: MediaStream, data: bytes) -> None:
    return None


engine = MediaCaptureEngine()
engine.register_adapter("ump", ump_adapter)
engine.register_adapter("hls", hls_adapter)
engine.register_adapter("dash", dash_adapter)
