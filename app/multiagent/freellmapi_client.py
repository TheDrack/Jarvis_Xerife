"""FreeLLMAPI client for low-cost, text-only Jarvis mini-agents.

FreeLLMAPI is an optional, self-hosted inference gateway. This module does not
replace ChatGPT/Claude as high-capability agents and does not execute tools.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

import httpx


class FreeLLMAPIError(RuntimeError):
    """A request to the configured FreeLLMAPI gateway failed."""


class FreeLLMAPIClient:
    """Small OpenAI-compatible client using the local FreeLLMAPI gateway."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = "auto",
        timeout_seconds: float = 45.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client

    @classmethod
    def from_env(cls) -> "FreeLLMAPIClient":
        """Build a client from explicit environment configuration."""
        api_key = os.getenv("FREELLMAPI_API_KEY", "").strip()
        base_url = os.getenv("FREELLMAPI_BASE_URL", "").strip()
        model = os.getenv("FREELLMAPI_MODEL", "").strip()
        if not api_key:
            # Prefer Groq to preserve Venice capacity for explicitly routed
            # Red/Blue tasks. Respect an explicit non-auto model override.
            api_key = os.getenv("GROQ_API_KEY", "").strip()
            if api_key:
                base_url = base_url or "https://api.groq.com/openai/v1"
                model = model if model and model.lower() != "auto" else os.getenv(
                    "GROQ_MODEL", "llama-3.3-70b-versatile"
                )
            else:
                api_key = os.getenv("VENICE_API_KEY", "").strip()
                if api_key:
                    base_url = base_url or "https://api.venice.ai/api/v1"
                    model = model if model and model.lower() != "auto" else "venice-uncensored-1-2"
        if not api_key:
            raise FreeLLMAPIError(
                "Configure FREELLMAPI_API_KEY, GROQ_API_KEY, or VENICE_API_KEY; "
                "mini-agent inference remains disabled."
            )
        try:
            timeout = float(os.getenv("FREELLMAPI_TIMEOUT_SECONDS", "45"))
        except ValueError as exc:
            raise FreeLLMAPIError("FREELLMAPI_TIMEOUT_SECONDS must be numeric.") from exc
        return cls(
            base_url=base_url or "http://127.0.0.1:3001/v1",
            api_key=api_key,
            model=model or "auto",
            timeout_seconds=timeout,
        )

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        """Return text and routing telemetry from an OpenAI-compatible completion."""
        if not messages:
            raise ValueError("messages must not be empty")
        if not 1 <= max_tokens <= 8192:
            raise ValueError("max_tokens must be between 1 and 8192")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")

        request_body = {
            "model": model or self.model,
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        owned_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=request_body,
                timeout=self.timeout_seconds,
            )
            if response.is_error:
                raise FreeLLMAPIError(
                    f"FreeLLMAPI returned HTTP {response.status_code}."
                )
            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise FreeLLMAPIError(
                    "FreeLLMAPI returned an invalid chat-completion response."
                ) from exc
            if not isinstance(content, str) or not content.strip():
                raise FreeLLMAPIError("FreeLLMAPI returned empty or non-text content.")
            return {
                "content": content.strip(),
                "model": data.get("model") or request_body["model"],
                "routed_via": response.headers.get("X-Routed-Via"),
                "fallback_attempts": _parse_nonnegative_int(
                    response.headers.get("X-Fallback-Attempts")
                ),
                "usage": data.get("usage") if isinstance(data.get("usage"), dict) else {},
            }
        except httpx.TimeoutException as exc:
            raise FreeLLMAPIError("FreeLLMAPI request timed out.") from exc
        except httpx.HTTPError as exc:
            raise FreeLLMAPIError("FreeLLMAPI gateway is unreachable.") from exc
        finally:
            if owned_client:
                client.close()


def _parse_nonnegative_int(value: str | None) -> int:
    try:
        return max(0, int(value)) if value is not None else 0
    except (TypeError, ValueError):
        return 0
