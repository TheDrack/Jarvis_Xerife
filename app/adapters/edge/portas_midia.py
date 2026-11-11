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


# UMP / HLS / DASH adapters (scaffolding)
def ump_adapter(stream: MediaStream, data: bytes) -> None:
    """Placeholder: parseia envelope UMP do YouTube (a implementar)."""
    # UMP frames: [type varint][size varint][payload]
    # Mantido como no-op seguro; decodificação real é fase posterior.
    return None


def hls_adapter(stream: MediaStream, data: bytes) -> None:
    return None


def dash_adapter(stream: MediaStream, data: bytes) -> None:
    return None


engine = MediaCaptureEngine()
engine.register_adapter("ump", ump_adapter)
engine.register_adapter("hls", hls_adapter)
engine.register_adapter("dash", dash_adapter)
