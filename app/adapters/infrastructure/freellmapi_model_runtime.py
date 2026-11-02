"""FreeLLMAPI implementation of the provider-neutral ModelRuntime port."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.application.ports.model_runtime import (
    ModelInvocationRequest,
    ModelInvocationResult,
    ModelRuntimeError,
    ModelUsage,
)
from app.multiagent.freellmapi_client import FreeLLMAPIClient, FreeLLMAPIError


class FreeLLMAPIModelRuntimeAdapter:
    """Adapt the OpenAI-compatible FreeLLMAPI client to the Jarvis model port."""

    supports_cancellation = False

    def __init__(
        self,
        client: FreeLLMAPIClient,
        *,
        provider_id: str = "unknown",
    ) -> None:
        if not isinstance(client, FreeLLMAPIClient):
            raise TypeError("client must be a FreeLLMAPIClient")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id must be a non-empty string")
        self.client = client
        self.provider_id = provider_id.strip().lower()

    def invoke(self, request: ModelInvocationRequest) -> ModelInvocationResult:
        if not isinstance(request, ModelInvocationRequest):
            raise TypeError("request must be a ModelInvocationRequest")
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]
        try:
            response = self.client.chat(
                messages,
                model=request.model_id,
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
                timeout_seconds=request.timeout_seconds,
            )
        except FreeLLMAPIError as exc:
            raise ModelRuntimeError(
                str(exc),
                code=exc.code,
                provider_id=self.provider_id,
                retryable=exc.retryable,
            ) from exc

        raw_usage = response.get("usage")
        usage_data: Mapping[str, Any] = raw_usage if isinstance(raw_usage, Mapping) else {}
        input_tokens = _usage_int(usage_data, "prompt_tokens", "input_tokens")
        output_tokens = _usage_int(usage_data, "completion_tokens", "output_tokens")
        total_tokens = _usage_int(usage_data, "total_tokens")
        if total_tokens is None and input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

        return ModelInvocationResult(
            provider_id=self.provider_id,
            model_id=str(response["model"]),
            content=str(response["content"]),
            usage=ModelUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            routed_via=_optional_text(response.get("routed_via")),
            fallback_attempts=_nonnegative_int(response.get("fallback_attempts")),
        )

    def cancel(self, request_id: str) -> bool:
        """FreeLLMAPI's synchronous REST client has no request-cancellation API."""
        return False


def _usage_int(usage: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _nonnegative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
