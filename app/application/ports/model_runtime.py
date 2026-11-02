"""Provider-neutral model invocation contracts for the Jarvis Harness."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol, runtime_checkable


_ALLOWED_ROLES = frozenset({"system", "user", "assistant", "tool"})


@dataclass(frozen=True)
class ModelMessage:
    """One normalized chat message independent of provider SDKs."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in _ALLOWED_ROLES:
            raise ValueError(f"unsupported model message role: {self.role!r}")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("model message content must be a non-empty string")


@dataclass(frozen=True)
class ModelInvocationRequest:
    """Immutable, bounded request accepted by any model runtime adapter."""

    messages: tuple[ModelMessage, ...]
    model_id: str | None = None
    temperature: float = 0.2
    max_output_tokens: int = 1200
    timeout_seconds: float | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.messages, (str, bytes)):
            raise TypeError("messages must be an iterable of ModelMessage objects")
        try:
            messages = tuple(self.messages)
        except TypeError as exc:
            raise TypeError("messages must be an iterable of ModelMessage objects") from exc
        if not messages:
            raise ValueError("messages must not be empty")
        if any(not isinstance(message, ModelMessage) for message in messages):
            raise TypeError("messages must contain only ModelMessage objects")
        object.__setattr__(self, "messages", messages)

        if self.model_id is not None and (
            not isinstance(self.model_id, str) or not self.model_id.strip()
        ):
            raise ValueError("model_id must be a non-empty string when provided")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not isfinite(self.temperature)
            or not 0.0 <= self.temperature <= 2.0
        ):
            raise ValueError("temperature must be finite and between 0 and 2")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens < 1
        ):
            raise ValueError("max_output_tokens must be a positive integer")
        if self.timeout_seconds is not None and (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        if self.correlation_id is not None and (
            not isinstance(self.correlation_id, str) or not self.correlation_id.strip()
        ):
            raise ValueError("correlation_id must be a non-empty string when provided")


@dataclass(frozen=True)
class ModelUsage:
    """Normalized token accounting; unknown provider fields remain unknown."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("input_tokens", "output_tokens", "total_tokens"):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")

    def to_dict(self) -> dict[str, int | None]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class ModelInvocationResult:
    """Normalized model output plus non-sensitive routing telemetry."""

    provider_id: str
    model_id: str
    content: str
    usage: ModelUsage = ModelUsage()
    routed_via: str | None = None
    fallback_attempts: int = 0
    request_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("provider_id", "model_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("content must be a non-empty string")
        if not isinstance(self.usage, ModelUsage):
            raise TypeError("usage must be a ModelUsage instance")
        if (
            isinstance(self.fallback_attempts, bool)
            or not isinstance(self.fallback_attempts, int)
            or self.fallback_attempts < 0
        ):
            raise ValueError("fallback_attempts must be a non-negative integer")


class ModelRuntimeError(RuntimeError):
    """Sanitized provider-neutral failure; never includes credentials or raw bodies."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        provider_id: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        if not isinstance(code, str) or not code.strip():
            raise ValueError("error code must be a non-empty string")
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id must be a non-empty string")
        if not isinstance(retryable, bool):
            raise TypeError("retryable must be a bool")
        self.code = code
        self.provider_id = provider_id
        self.retryable = retryable


@runtime_checkable
class ModelRuntime(Protocol):
    """Synchronous invocation boundary implemented by provider adapters."""

    supports_cancellation: bool

    def invoke(self, request: ModelInvocationRequest) -> ModelInvocationResult:
        """Execute one bounded model request."""

    def cancel(self, request_id: str) -> bool:
        """Cancel a running request; return False when unsupported or unknown."""
