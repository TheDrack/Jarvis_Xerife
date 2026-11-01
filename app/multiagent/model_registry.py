"""Provider-neutral model/runtime contracts and in-process registry.

This module describes callable intelligence endpoints without importing any
provider SDK. Credentials and transport clients stay inside provider adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from threading import RLock
from types import MappingProxyType
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ModelProfile:
    """Public capability and operational metadata for one model/runtime."""

    model_id: str
    provider_id: str
    runtime_kind: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    modalities: frozenset[str] = field(default_factory=lambda: frozenset({"text"}))
    available: bool = True
    max_concurrency: int = 1
    context_window: int | None = None
    max_output_tokens: int | None = None
    estimated_cost_per_1k_tokens: float | None = None
    estimated_latency_ms: float | None = None
    trust_level: str = "standard"
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("model_id", "provider_id", "runtime_kind", "trust_level"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not isinstance(self.available, bool):
            raise TypeError("available must be a bool")
        if isinstance(self.max_concurrency, bool) or not isinstance(self.max_concurrency, int):
            raise TypeError("max_concurrency must be an integer")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")

        for field_name in ("context_window", "max_output_tokens"):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise TypeError(f"{field_name} must be an integer when provided")
                if value < 1:
                    raise ValueError(f"{field_name} must be positive when provided")

        for field_name in ("estimated_cost_per_1k_tokens", "estimated_latency_ms"):
            value = getattr(self, field_name)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{field_name} must be numeric when provided")
                if not isfinite(value) or value < 0:
                    raise ValueError(f"{field_name} must be finite and non-negative")

        for field_name in ("capabilities", "modalities"):
            values = getattr(self, field_name)
            try:
                normalized = frozenset(values)
            except TypeError as exc:
                raise TypeError(f"{field_name} must be an iterable of strings") from exc
            if any(not isinstance(item, str) or not item.strip() for item in normalized):
                raise ValueError(f"{field_name} must contain only non-empty strings")
            object.__setattr__(self, field_name, normalized)

        if not self.modalities:
            raise ValueError("at least one modality must be declared")

        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping of strings to strings")
        metadata = dict(self.metadata)
        if any(
            not isinstance(key, str) or not key.strip()
            or not isinstance(value, str)
            for key, value in metadata.items()
        ):
            raise ValueError("metadata keys and values must be strings; keys cannot be empty")
        object.__setattr__(self, "metadata", MappingProxyType(metadata))


class ModelRegistry:
    """Thread-safe registry; registration does not imply authorization."""

    def __init__(self, profiles: Iterable[ModelProfile] = ()) -> None:
        self._lock = RLock()
        self._profiles: dict[str, ModelProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: ModelProfile, *, replace: bool = False) -> None:
        if not isinstance(profile, ModelProfile):
            raise TypeError("profile must be a ModelProfile")
        if not isinstance(replace, bool):
            raise TypeError("replace must be a bool")
        with self._lock:
            if profile.model_id in self._profiles and not replace:
                raise ValueError(f"model already registered: {profile.model_id}")
            self._profiles[profile.model_id] = profile

    def unregister(self, model_id: str) -> bool:
        with self._lock:
            return self._profiles.pop(model_id, None) is not None

    def get(self, model_id: str) -> ModelProfile | None:
        with self._lock:
            return self._profiles.get(model_id)

    def list_profiles(self) -> tuple[ModelProfile, ...]:
        with self._lock:
            return tuple(self._profiles[key] for key in sorted(self._profiles))

    def eligible(
        self,
        *,
        required_capabilities: Iterable[str] = (),
        required_modalities: Iterable[str] = ("text",),
        provider_ids: Iterable[str] | None = None,
    ) -> tuple[ModelProfile, ...]:
        """Return available profiles satisfying declared task requirements.

        An omitted or empty provider_ids value means no provider restriction.
        Selection among eligible profiles (cost/latency/load policy) belongs
        to the scheduler.
        """
        capabilities = frozenset(required_capabilities)
        modalities = frozenset(required_modalities)
        providers = None if provider_ids is None else frozenset(provider_ids)
        if not providers:
            providers = None
        with self._lock:
            candidates = tuple(self._profiles.values())
        return tuple(
            profile for profile in sorted(candidates, key=lambda item: item.model_id)
            if profile.available
            and capabilities.issubset(profile.capabilities)
            and modalities.issubset(profile.modalities)
            and (providers is None or profile.provider_id in providers)
        )
