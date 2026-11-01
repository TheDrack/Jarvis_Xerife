"""Provider-neutral model/runtime contracts and in-process registry.

This module describes callable intelligence endpoints without importing any
provider SDK. Credentials and transport clients stay inside provider adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
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
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        for field_name in ("context_window", "max_output_tokens"):
            value = getattr(self, field_name)
            if value is not None and value < 1:
                raise ValueError(f"{field_name} must be positive when provided")
        for field_name in ("estimated_cost_per_1k_tokens", "estimated_latency_ms"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative when provided")
        if not self.modalities:
            raise ValueError("at least one modality must be declared")
        if any(not item.strip() for item in self.capabilities | self.modalities):
            raise ValueError("capabilities and modalities must contain non-empty values")


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

        An empty provider_ids value means no provider restriction. Selection
        among eligible profiles (cost/latency/load policy) belongs to scheduler.
        """
        capabilities = frozenset(required_capabilities)
        modalities = frozenset(required_modalities)
        providers = None if provider_ids is None else frozenset(provider_ids)
        with self._lock:
            candidates = tuple(self._profiles.values())
        return tuple(
            profile for profile in sorted(candidates, key=lambda item: item.model_id)
            if profile.available
            and capabilities.issubset(profile.capabilities)
            and modalities.issubset(profile.modalities)
            and (providers is None or profile.provider_id in providers)
        )
