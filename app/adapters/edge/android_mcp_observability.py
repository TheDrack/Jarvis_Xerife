"""Opt-in, metadata-only ASGI observability for the Android MCP boundary."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

_DEFAULT_LOG = Path.home() / ".local/state/jarvis-android-mcp/observability.jsonl"
_MAX_LOG_BYTES = 1_048_576
_BACKUP_COUNT = 3
_LOCK = RLock()


class MetadataObservabilityMiddleware:
    """Observe HTTP metadata without retaining headers, query strings, or bodies.

    The middleware counts body bytes while forwarding ASGI messages unchanged.
    Logging is deliberately fail-open: an observability I/O error never breaks MCP.
    """

    def __init__(self, app: Any, *, log_path: str | Path = _DEFAULT_LOG) -> None:
        self.app = app
        self.log_path = Path(log_path).expanduser()

    @classmethod
    def from_environment(cls, app: Any) -> MetadataObservabilityMiddleware | None:
        if os.environ.get("JARVIS_ANDROID_MCP_OBSERVABILITY", "").strip() != "1":
            return None
        configured_path = os.environ.get(
            "JARVIS_ANDROID_MCP_OBSERVABILITY_LOG", ""
        ).strip()
        return cls(app, log_path=configured_path or _DEFAULT_LOG)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        started = time.monotonic()
        request_bytes = 0
        response_bytes = 0
        status_code: int | None = None

        async def observed_receive() -> dict:
            nonlocal request_bytes
            message = await receive()
            if message.get("type") == "http.request":
                request_bytes += len(message.get("body", b""))
            return message

        async def observed_send(message: dict) -> None:
            nonlocal response_bytes, status_code
            if message.get("type") == "http.response.start":
                status_code = message.get("status")
            elif message.get("type") == "http.response.body":
                response_bytes += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, observed_receive, observed_send)
        finally:
            elapsed_ms = round((time.monotonic() - started) * 1000, 3)
            route = scope.get("route")
            route_template = getattr(route, "path", None)
            if not isinstance(route_template, str):
                route_template = "unmatched"
            common = {
                "timestamp": datetime.now(UTC).isoformat(),
                "request_id": request_id,
                "transport": "asgi-http",
                "protocol": str(scope.get("http_version", "unknown")),
                "method": str(scope.get("method", "unknown")),
                "route": route_template[:256],
                "latency_ms": elapsed_ms,
            }
            self._emit(
                {**common, "direction": "inbound", "request_bytes": request_bytes}
            )
            self._emit(
                {
                    **common,
                    "direction": "outbound",
                    "status_code": status_code,
                    "response_bytes": response_bytes,
                }
            )

    def _emit(self, record: dict[str, Any]) -> None:
        try:
            self._write_record(record)
        except (OSError, ValueError, TypeError):
            # Observability must not make the MCP transport unavailable.
            return

    def _write_record(self, record: dict[str, Any]) -> None:
        encoded = (
            json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        ).encode()
        path = self.log_path
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.parent.is_symlink() or path.is_symlink():
                raise ValueError("observability path must not traverse a symbolic link")
            os.chmod(path.parent, 0o700)
            if path.exists() and path.stat().st_size + len(encoded) > _MAX_LOG_BYTES:
                for index in range(_BACKUP_COUNT, 0, -1):
                    source = path.with_name(f"{path.name}.{index}")
                    destination = path.with_name(f"{path.name}.{index + 1}")
                    if source.is_symlink() or destination.is_symlink():
                        raise ValueError(
                            "observability rotation path must not be a symbolic link"
                        )
                    if index == _BACKUP_COUNT:
                        source.unlink(missing_ok=True)
                    elif source.exists():
                        os.replace(source, destination)
                if path.exists():
                    os.replace(path, path.with_name(f"{path.name}.1"))
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags, 0o600)
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "ab") as stream:
                    descriptor = -1
                    stream.write(encoded)
                    stream.flush()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
