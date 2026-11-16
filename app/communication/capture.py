"""Append-only JSONL capture with recursive secret redaction."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import RLock
from typing import Any

from app.communication.contracts import CommunicationCaptureRecord, CommunicationRequest

_SECRET_NAMES = {
    "authorization",
    "proxyauthorization",
    "cookie",
    "setcookie",
    "token",
    "accesstoken",
    "refreshtoken",
    "password",
    "passwd",
    "secret",
    "apikey",
    "clientsecret",
    "credential",
    "credentials",
    "privatekey",
    "sessionid",
}
_REDACTED = "[REDACTED]"
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:access_token|refresh_token|token|api[_-]?key|client_secret|password)=)[^&#\s]+"
)
_BEARER_SECRET = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+=*")


def _is_secret_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return (
        normalized in _SECRET_NAMES
        or any(
            part in normalized
            for part in (
                "token",
                "password",
                "passwd",
                "secret",
                "credential",
                "cookie",
                "authorization",
            )
        )
        or normalized.endswith("key")
    )


def _redact_string(value: str) -> str:
    return _BEARER_SECRET.sub(
        r"\1[REDACTED]", _QUERY_SECRET.sub(r"\1[REDACTED]", value)
    )


def redact_secrets(value: Any) -> Any:
    """Return a JSON-safe deep copy with credential-like fields removed."""
    if isinstance(value, dict):
        return {
            str(key): (_REDACTED if _is_secret_key(key) else redact_secrets(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    raise ValueError("communication capture data must be JSON-compatible")


class CommunicationCapture:
    """Persist sanitized operation templates; never persist live credentials."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._lock = RLock()

    def record(
        self, request: CommunicationRequest, response: Any = None
    ) -> CommunicationCaptureRecord:
        safe_request = redact_secrets(request.model_dump())
        safe_response = redact_secrets(response)
        record = CommunicationCaptureRecord(
            request=safe_request, response=safe_response
        )
        encoded = record.model_dump_json()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.parent.is_symlink() or self.path.is_symlink():
                raise ValueError("capture path must not traverse a symbolic link")
            try:
                os.chmod(self.path.parent, 0o700)
            except OSError:
                pass
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.path, flags, 0o600)
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
                    descriptor = -1
                    stream.write(encoded + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        return record

    def get(self, capture_id: str) -> CommunicationCaptureRecord:
        if not isinstance(capture_id, str) or not capture_id.strip():
            raise ValueError("capture_id must be non-empty")
        with self._lock:
            if self.path.is_symlink():
                raise ValueError("capture path must not be a symbolic link")
            if not self.path.exists():
                raise LookupError(f"capture not found: {capture_id}")
            with self.path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("capture_id") == capture_id:
                            return CommunicationCaptureRecord.model_validate(data)
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        continue
        raise LookupError(f"capture not found: {capture_id}")
