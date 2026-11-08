"""Optional HTTP adapter for a self-hosted Laya decision service."""
from __future__ import annotations
import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

class LayaDecisionError(RuntimeError):
    """Sanitized Laya transport or response failure."""

class LayaDecisionAdapter:
    """Calls Laya's documented POST /predict JSON endpoint."""
    def __init__(self, base_url: str, *, api_key: str | None = None,
                 timeout_seconds: float = 0.8, opener=urlopen) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty URL")
        parsed = urlsplit(base_url)
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Laya endpoint must be an HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in loopback_hosts:
            raise ValueError("Laya endpoint must use loopback HTTP or HTTPS")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener

    @classmethod
    def from_env(cls) -> "LayaDecisionAdapter":
        return cls(
            os.getenv("JARVIS_LAYA_BASE_URL", "http://127.0.0.1:8000"),
            api_key=os.getenv("JARVIS_LAYA_API_KEY") or None,
            timeout_seconds=float(os.getenv("JARVIS_LAYA_TIMEOUT_SECONDS", "0.8")),
        )

    def decide(self, state: Mapping[str, Any], questions: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(state, Mapping) or not isinstance(questions, Mapping):
            raise TypeError("state and questions must be mappings")
        payload = json.dumps({"state": dict(state), "questions": dict(questions)},
                             ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(f"{self.base_url}/predict", data=payload, headers=headers, method="POST")
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise LayaDecisionError("Laya response exceeded the 1 MB limit")
            decoded = json.loads(raw.decode("utf-8"))
        except HTTPError as exc:
            raise LayaDecisionError(f"Laya returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise LayaDecisionError("Laya endpoint unavailable or timed out") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise LayaDecisionError("Laya returned invalid JSON") from None
        if not isinstance(decoded, dict) or not isinstance(decoded.get("answers"), dict):
            raise LayaDecisionError("Laya response is missing the answers object")
        return decoded
