# -*- coding: utf-8 -*-
"""Camada de entrega de mídia decodificada para consumidores (stream IA, player desktop).

Fornece filas limitadas por sessão para PCM (áudio) e frames (vídeo), com
timestamps, backpressure (descarte do mais antigo) e sincronização básica.
Os bytes vêm de ``portas_midia.decode_stream`` (requer ffmpeg).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from app.adapters.edge.portas_midia import engine as media_engine, decode_stream, decode_available


@dataclass
class AudioFrame:
    stream_id: str
    timestamp: float
    pcm_path: str
    sample_rate: int = 0
    channels: int = 0
    sequence: int = 0


@dataclass
class VideoFrame:
    stream_id: str
    timestamp: float
    image_path: str
    width: int = 0
    height: int = 0
    sequence: int = 0


class MediaDeliveryBus:
    """Barramento de entrega com filas limitadas e backpressure."""

    def __init__(self, *, audio_queue_size: int = 64, video_queue_size: int = 32) -> None:
        self._lock = threading.RLock()
        self._audio: Deque[AudioFrame] = deque(maxlen=max(4, int(audio_queue_size)))
        self._video: Deque[VideoFrame] = deque(maxlen=max(4, int(video_queue_size)))
        self._audio_seq = 0
        self._video_seq = 0
        self._started_at: float | None = None
        self._active = False

    def start(self) -> dict[str, Any]:
        with self._lock:
            self._active = True
            self._started_at = time.monotonic()
            return {"success": True, "active": True}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._active = False
            return {"success": True, "active": False, "audio_queued": len(self._audio), "video_queued": len(self._video)}

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def push_audio(self, frame: AudioFrame) -> None:
        with self._lock:
            self._audio_seq += 1
            frame.sequence = self._audio_seq
            self._audio.append(frame)

    def push_video(self, frame: VideoFrame) -> None:
        with self._lock:
            self._video_seq += 1
            frame.sequence = self._video_seq
            self._video.append(frame)

    def latest_audio(self, *, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            sel = list(self._audio)[-max(1, min(int(limit), 64)):]
            return [{"stream_id": f.stream_id, "timestamp": f.timestamp, "pcm_path": f.pcm_path, "sequence": f.sequence} for f in sel]

    def latest_video(self, *, limit: int = 8) -> list[dict[str, Any]]:
        with self._lock:
            sel = list(self._video)[-max(1, min(int(limit), 64)):]
            return [{"stream_id": f.stream_id, "timestamp": f.timestamp, "image_path": f.image_path, "sequence": f.sequence} for f in sel]

    def pull_for_ai(self, *, audio_limit: int = 4, video_limit: int = 4) -> dict[str, Any]:
        """Snapshot para o stream IA: últimos frames de áudio e vídeo com timestamps."""
        with self._lock:
            return {
                "success": True,
                "active": self._active,
                "audio": self.latest_audio(limit=audio_limit),
                "video": self.latest_video(limit=video_limit),
                "audio_queued": len(self._audio),
                "video_queued": len(self._video),
            }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "success": True,
                "active": self._active,
                "started_at": self._started_at,
                "audio_queued": len(self._audio),
                "video_queued": len(self._video),
                "decode_available": decode_available(),
            }

    def clear(self) -> dict[str, Any]:
        with self._lock:
            a, v = len(self._audio), len(self._video)
            self._audio.clear()
            self._video.clear()
            return {"success": True, "cleared_audio": a, "cleared_video": v}


bus = MediaDeliveryBus()


def registrar_entrega_midia(mcp: Any, tracked_action: Any) -> None:
    @mcp.tool()
    @tracked_action("Iniciando barramento de entrega de mídia")
    def portas_midia_entrega_iniciar() -> dict[str, Any]:
        """Inicia o barramento de entrega de mídia decodificada."""
        return bus.start()

    @mcp.tool()
    @tracked_action("Parando barramento de entrega de mídia")
    def portas_midia_entrega_parar() -> dict[str, Any]:
        """Para o barramento de entrega."""
        return bus.stop()

    @mcp.tool()
    @tracked_action("Status do barramento de entrega de mídia")
    def portas_midia_entrega_status() -> dict[str, Any]:
        """Status do barramento (filas, decode disponível)."""
        return bus.status()

    @mcp.tool()
    @tracked_action("Últimos frames de áudio entregues")
    def portas_midia_entrega_audio(limit: int = 8) -> dict[str, Any]:
        """Retorna últimos frames de áudio entregues."""
        return {"success": True, "frames": bus.latest_audio(limit=limit)}

    @mcp.tool()
    @tracked_action("Últimos frames de vídeo entregues")
    def portas_midia_entrega_video(limit: int = 8) -> dict[str, Any]:
        """Retorna últimos frames de vídeo entregues."""
        return {"success": True, "frames": bus.latest_video(limit=limit)}

    @mcp.tool()
    @tracked_action("Snapshot para stream IA")
    def portas_midia_entrega_pull_ia(audio_limit: int = 4, video_limit: int = 4) -> dict[str, Any]:
        """Snapshot de áudio+vídeo para o stream IA."""
        return bus.pull_for_ai(audio_limit=audio_limit, video_limit=video_limit)

    @mcp.tool()
    @tracked_action("Ingerindo stream decodificado na entrega")
    def portas_midia_entrega_ingerir(stream_id: str) -> dict[str, Any]:
        """Decodifica um stream capturado e ingere na bus de entrega."""
        return ingest_decoded(stream_id)

    @mcp.tool()
    @tracked_action("Limpando barramento de entrega")
    def portas_midia_entrega_limpar() -> dict[str, Any]:
        """Limpa filas de entrega."""
        return bus.clear()


def ingest_decoded(stream_id: str) -> dict[str, Any]:
    """Decodifica um stream e ingere na bus (requer ffmpeg)."""
    if not decode_available():
        return {"success": False, "available": False, "reason": "ffmpeg não encontrado"}
    audio_res = decode_stream(stream_id, mode="audio")
    if audio_res.get("output"):
        bus.push_audio(AudioFrame(stream_id=stream_id, timestamp=time.time(), pcm_path=audio_res["output"]))
    frames_res = decode_stream(stream_id, mode="frames")
    for p in frames_res.get("frames", [])[:4]:
        bus.push_video(VideoFrame(stream_id=stream_id, timestamp=time.time(), image_path=p))
    return {
        "success": True,
        "stream_id": stream_id,
        "audio": audio_res.get("output"),
        "frames": len(frames_res.get("frames", [])),
    }
