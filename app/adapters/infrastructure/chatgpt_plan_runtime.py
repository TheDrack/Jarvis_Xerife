"""Official Sign in with ChatGPT plan-usage runtime adapter.

Uses the public Responses API with OAuth credentials issued for this local
Jarvis installation. Never calls ChatGPT web-app backend endpoints.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from math import isfinite
from pathlib import Path
from typing import Any

import httpx

from app.application.ports.model_runtime import (
    ModelInvocationRequest,
    ModelInvocationResult,
    ModelRuntimeError,
    ModelUsage,
)

API_BASE_URL = "https://api.openai.com/v1"
PLAN_USAGE_SCOPE = "chatgpt.tokens.use.direct"
RESOURCE_INVOKE_SCOPE = "resource.invoke"
MAX_OUTPUT_TOKENS = 8192
_ALLOWED_INPUT_ROLES = frozenset({"system", "developer", "user", "assistant"})


class ChatGPTPlanError(RuntimeError):
    """Sanitized provider failure with stable retry metadata."""

    def __init__(self, message: str, *, code: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ChatGPTPlanCredentialStore:
    """Owner-only local credential storage for one ChatGPT connection."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("JARVIS_CHATGPT_AUTH_FILE", "").strip()
        self.path = (
            Path(configured).expanduser()
            if configured
            else (Path.home() / ".config" / "jarvis" / "chatgpt" / "profile.json")
        )

    def save(self, profile: Mapping[str, Any]) -> None:
        if not isinstance(profile, Mapping):
            raise TypeError("profile must be a mapping")
        if (
            not isinstance(profile.get("access_token"), str)
            or not profile["access_token"].strip()
        ):
            raise ValueError("ChatGPT profile requires an access token")
        scopes = profile.get("scopes")
        if (
            not isinstance(scopes, (list, tuple, set))
            or PLAN_USAGE_SCOPE not in scopes
            or RESOURCE_INVOKE_SCOPE not in scopes
        ):
            raise ValueError(
                "ChatGPT profile lacks the required plan-usage permissions"
            )
        for key in ("client_id", "subject"):
            if not isinstance(profile.get(key), str) or not profile[key].strip():
                raise ValueError(f"ChatGPT profile requires {key}")
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink():
            raise ValueError("credential directory must not be a symbolic link")
        os.chmod(parent, 0o700)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".chatgpt-", suffix=".tmp", dir=parent
        )
        temporary = Path(temporary_name)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    dict(profile), stream, ensure_ascii=False, separators=(",", ":")
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            try:
                directory_fd = os.open(parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        if self.path.is_symlink():
            raise ValueError("credential file must not be a symbolic link")
        if self.path.stat().st_mode & 0o077:
            raise PermissionError("ChatGPT credential file permissions must be 0600")
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ChatGPTPlanError(
                "Local ChatGPT credential profile is unreadable.",
                code="credential_store_error",
            ) from exc
        if not isinstance(value, dict):
            raise ChatGPTPlanError(
                "Local ChatGPT credential profile has an invalid format.",
                code="credential_store_error",
            )
        return value

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class ChatGPTPlanClient:
    """Responses API client authenticated by SIWC OAuth tokens."""

    def __init__(
        self,
        *,
        access_token: str,
        model: str | None = None,
        base_url: str = API_BASE_URL,
        timeout_seconds: float = 90.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("access_token must not be empty")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError("model must be a non-empty string or None")
        if base_url != API_BASE_URL:
            raise ValueError(
                "base_url must use the official OpenAI Responses API origin"
            )
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, (int, float)
        ):
            raise ValueError("timeout_seconds must be numeric")
        if not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self._access_token = access_token
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self._http = http_client or httpx.Client(timeout=self.timeout_seconds)
        self._owns_http = http_client is None

    def set_access_token(self, access_token: str) -> None:
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("access_token must not be empty")
        self._access_token = access_token

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> ChatGPTPlanClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _headers(self, accept: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": accept,
        }

    def list_models(self) -> tuple[dict[str, str], ...]:
        """Return account-visible model slugs in provider order."""
        try:
            response = self._http.get(
                f"{self.base_url}/models",
                headers=self._headers("application/json"),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ChatGPTPlanError(
                "ChatGPT model discovery timed out.", code="timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatGPTPlanError(
                "ChatGPT model discovery could not reach the service.",
                code="transport_error",
                retryable=True,
            ) from exc
        if response.is_error:
            raise _http_error(response.status_code)
        try:
            entries = response.json()["models"]
            if not isinstance(entries, list):
                raise TypeError
            return tuple(
                {
                    "slug": item["slug"],
                    "display_name": str(item.get("display_name") or item["slug"]),
                }
                for item in entries
                if isinstance(item, dict)
                and item.get("visibility") == "list"
                and isinstance(item.get("slug"), str)
                and item["slug"].strip()
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise ChatGPTPlanError(
                "ChatGPT returned an invalid model catalog.", code="invalid_response"
            ) from exc

    def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        model: str | None = None,
        max_output_tokens: int = 1200,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Generate one completed response without server-side conversation state."""
        normalized = _validate_messages(messages)
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS
        ):
            raise ValueError(
                f"max_output_tokens must be between 1 and {MAX_OUTPUT_TOKENS}"
            )
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError("model must be a non-empty string or None")
        if temperature is not None and (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not isfinite(temperature)
            or not 0.0 <= temperature <= 2.0
        ):
            raise ValueError("temperature must be finite and between 0 and 2")
        selected_model = model or self.model
        if not selected_model:
            models = self.list_models()
            if not models:
                raise ChatGPTPlanError(
                    "No models are available for this ChatGPT account.",
                    code="no_models",
                )
            selected_model = models[0]["slug"]
        body = {
            "model": selected_model,
            "input": normalized,
            "max_output_tokens": max_output_tokens,
            "store": False,
            "stream": True,
        }
        if temperature is not None:
            body["temperature"] = temperature
        chunks: list[str] = []
        completed: Mapping[str, Any] | None = None
        request_id: str | None = None
        try:
            with self._http.stream(
                "POST",
                f"{self.base_url}/responses",
                headers=self._headers("text/event-stream"),
                json=body,
                timeout=float(timeout),
            ) as response:
                request_id = _header(
                    response.headers, "x-request-id", "openai-request-id"
                )
                if response.is_error:
                    raise _http_error(response.status_code)
                for line in response.iter_lines():
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw or raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ChatGPTPlanError(
                            "ChatGPT returned a malformed streaming event.",
                            code="invalid_stream",
                        ) from exc
                    if not isinstance(event, dict):
                        continue
                    kind = event.get("type")
                    if kind == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            chunks.append(delta)
                    elif kind == "response.failed":
                        response_data = event.get("response")
                        error_data = (
                            response_data.get("error")
                            if isinstance(response_data, dict)
                            else None
                        )
                        provider_code = (
                            error_data.get("code")
                            if isinstance(error_data, dict)
                            else None
                        )
                        code = _classify_provider_code(provider_code)
                        raise ChatGPTPlanError(_safe_message(code), code=code)
                    elif kind == "response.incomplete":
                        raise ChatGPTPlanError(
                            "ChatGPT ended the response before completion.",
                            code="incomplete_response",
                        )
                    elif kind == "response.completed":
                        value = event.get("response")
                        if isinstance(value, Mapping):
                            completed = value
                            break
        except ChatGPTPlanError:
            raise
        except httpx.TimeoutException as exc:
            raise ChatGPTPlanError(
                "ChatGPT response timed out.", code="timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise ChatGPTPlanError(
                "ChatGPT response stream was interrupted.", code="transport_error"
            ) from exc
        if completed is None:
            raise ChatGPTPlanError(
                "ChatGPT stream ended without response.completed.",
                code="incomplete_stream",
            )
        content = "".join(chunks).strip()
        if not content:
            raise ChatGPTPlanError(
                "ChatGPT returned an empty text response.", code="empty_response"
            )
        usage = completed.get("usage")
        usage_data = usage if isinstance(usage, Mapping) else {}
        input_tokens = _nonnegative_int(usage_data.get("input_tokens"))
        output_tokens = _nonnegative_int(usage_data.get("output_tokens"))
        total_tokens = _nonnegative_int(usage_data.get("total_tokens"))
        if (
            total_tokens is None
            and input_tokens is not None
            and output_tokens is not None
        ):
            total_tokens = input_tokens + output_tokens
        return {
            "content": content,
            "model": str(completed.get("model") or selected_model),
            "request_id": _optional_text(completed.get("id")) or request_id,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
        }


class ChatGPTPlanModelRuntimeAdapter:
    """Adapt ChatGPT plan usage to Jarvis' provider-neutral model runtime."""

    supports_cancellation = False
    provider_id = "chatgpt_plan"

    def __init__(
        self,
        client: ChatGPTPlanClient,
        *,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(client, ChatGPTPlanClient):
            raise TypeError("client must be a ChatGPTPlanClient")
        if token_provider is not None and not callable(token_provider):
            raise TypeError("token_provider must be callable")
        self.client = client
        self.token_provider = token_provider

    def invoke(self, request: ModelInvocationRequest) -> ModelInvocationResult:
        if not isinstance(request, ModelInvocationRequest):
            raise TypeError("request must be a ModelInvocationRequest")
        messages = tuple(
            {"role": item.role, "content": item.content} for item in request.messages
        )
        try:
            if self.token_provider is not None:
                self.client.set_access_token(self.token_provider())
            result = self.client.generate(
                messages,
                model=request.model_id,
                max_output_tokens=request.max_output_tokens,
                timeout_seconds=request.timeout_seconds,
                # Keep the Responses API model default unless a caller explicitly
                # overrides the ModelInvocationRequest default of 0.2.
                temperature=(
                    None if request.temperature == 0.2 else request.temperature
                ),
            )
        except ChatGPTPlanError as exc:
            raise ModelRuntimeError(
                str(exc),
                code=exc.code,
                provider_id=self.provider_id,
                retryable=exc.retryable,
            ) from exc
        except ValueError as exc:
            raise ModelRuntimeError(
                "ChatGPT rejected the normalized invocation limits.",
                code="invalid_request",
                provider_id=self.provider_id,
                retryable=False,
            ) from exc
        usage = result["usage"]
        return ModelInvocationResult(
            provider_id=self.provider_id,
            model_id=result["model"],
            content=result["content"],
            request_id=result.get("request_id"),
            usage=ModelUsage(
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
        )

    def close(self) -> None:
        self.client.close()

    def cancel(self, request_id: str) -> bool:
        return False


def _validate_messages(messages: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    if isinstance(messages, (str, bytes)) or not messages:
        raise ValueError("messages must be a non-empty sequence")
    normalized = []
    for message in messages:
        if not isinstance(message, Mapping):
            raise TypeError("each message must be a mapping")
        role, content = message.get("role"), message.get("content")
        if not isinstance(role, str) or role not in _ALLOWED_INPUT_ROLES:
            raise ValueError(
                "message role is not supported by the Responses API adapter"
            )
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be a non-empty string")
        normalized.append({"role": role, "content": content})
    return normalized


def _http_error(status: int) -> ChatGPTPlanError:
    code = (
        "reauthorization_required"
        if status == 401
        else "permission_denied"
        if status == 403
        else "usage_limit"
        if status == 429
        else "provider_unavailable"
        if status >= 500
        else "provider_rejected"
    )
    return ChatGPTPlanError(_safe_message(code), code=code, retryable=status >= 500)


def _classify_provider_code(value: Any) -> str:
    if isinstance(value, str) and value.startswith("subscription_sharing_usage_"):
        return "usage_limit"
    if isinstance(value, str) and value in {
        "invalid_api_key",
        "invalid_token",
        "token_expired",
    }:
        return "reauthorization_required"
    return "provider_error"


def _safe_message(code: str) -> str:
    return {
        "reauthorization_required": "The ChatGPT connection must be authorized again.",
        "permission_denied": "The ChatGPT account has not granted the required permission.",
        "usage_limit": "The ChatGPT plan usage limit was reached or is unavailable.",
        "provider_unavailable": "ChatGPT is temporarily unavailable.",
        "provider_rejected": "ChatGPT rejected the request.",
        "provider_error": "ChatGPT could not complete the request.",
    }.get(code, "ChatGPT request failed.")


def _header(headers: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = headers.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _nonnegative_int(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )
