"""Typed semantic aliases for capabilities, with authorization and audit preserved.

Aliases are stable internal names for operations, not a way to disguise or bypass
policy decisions. Every execution is authorized against the canonical capability
ID and audit records include both the alias and canonical ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


class AliasRegistryError(ValueError):
    """Base error for invalid alias registry operations."""


class UnknownAliasError(AliasRegistryError):
    """Raised when an alias has not been registered."""


class DuplicateAliasError(AliasRegistryError):
    """Raised when an alias would overwrite an existing mapping."""


class CapabilityDenied(PermissionError):
    """Raised when the authorization callback denies a capability."""


@dataclass(frozen=True)
class Capability:
    """Canonical operation metadata and its callable implementation."""

    capability_id: str
    description: str
    handler: Callable[[Mapping[str, Any]], Any]
    required_permission: str = "capability.execute"
    requires_confirmation: bool = False


@dataclass(frozen=True)
class AliasBinding:
    """An internal semantic name bound to a canonical capability."""

    alias: str
    capability_id: str
    intent: str


class CapabilityAliasRegistry:
    """Resolve intent aliases while enforcing canonical authorization and audit.

    The registry deliberately does not infer permissions from an alias. Callers
    must supply authorization and audit callbacks at execution time, ensuring
    policy remains outside the naming layer and cannot be bypassed by renaming.
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._aliases: dict[str, AliasBinding] = {}

    @staticmethod
    def _validate_name(value: str, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise AliasRegistryError(f"{label} must be a non-empty string")
        return value.strip()

    def register_capability(self, capability: Capability) -> None:
        capability_id = self._validate_name(capability.capability_id, "capability_id")
        if capability_id in self._capabilities:
            raise DuplicateAliasError(f"Capability already registered: {capability_id}")
        if not callable(capability.handler):
            raise AliasRegistryError("Capability handler must be callable")
        self._capabilities[capability_id] = capability

    def register_alias(self, alias: str, capability_id: str, intent: str) -> AliasBinding:
        alias = self._validate_name(alias, "alias")
        capability_id = self._validate_name(capability_id, "capability_id")
        intent = self._validate_name(intent, "intent")
        if alias in self._aliases:
            raise DuplicateAliasError(f"Alias already registered: {alias}")
        if capability_id not in self._capabilities:
            raise UnknownAliasError(f"Unknown canonical capability: {capability_id}")
        binding = AliasBinding(alias=alias, capability_id=capability_id, intent=intent)
        self._aliases[alias] = binding
        return binding

    def resolve(self, alias: str) -> tuple[AliasBinding, Capability]:
        alias = self._validate_name(alias, "alias")
        try:
            binding = self._aliases[alias]
        except KeyError as exc:
            raise UnknownAliasError(f"Unknown alias: {alias}") from exc
        return binding, self._capabilities[binding.capability_id]

    def execute(
        self,
        alias: str,
        payload: Mapping[str, Any] | None = None,
        *,
        authorize: Callable[[str, str], bool],
        audit: Callable[[Mapping[str, Any]], None],
        confirmed: bool = False,
    ) -> Any:
        """Execute an alias only after canonical authorization and confirmation.

        authorize receives (canonical capability ID, required permission).
        Audit is emitted for denied and successful attempts; audit callback errors
        are not swallowed. Confirmation is an explicit caller-provided signal.
        """
        binding, capability = self.resolve(alias)
        record = {
            "event": "capability_execution",
            "alias": binding.alias,
            "intent": binding.intent,
            "capability_id": capability.capability_id,
            "required_permission": capability.required_permission,
            "status": "pending",
        }
        if not authorize(capability.capability_id, capability.required_permission):
            record["status"] = "denied"
            audit(record)
            raise CapabilityDenied(f"Not authorized: {capability.capability_id}")
        if capability.requires_confirmation and not confirmed:
            record["status"] = "confirmation_required"
            audit(record)
            raise CapabilityDenied(f"Explicit confirmation required: {capability.capability_id}")
        result = capability.handler(payload or {})
        record["status"] = "success"
        audit(record)
        return result

    def describe(self) -> list[dict[str, str | bool]]:
        """Return inspectable alias metadata without exposing callable objects."""
        return [
            {
                "alias": binding.alias,
                "intent": binding.intent,
                "capability_id": binding.capability_id,
                "required_permission": self._capabilities[binding.capability_id].required_permission,
                "requires_confirmation": self._capabilities[binding.capability_id].requires_confirmation,
            }
            for binding in self._aliases.values()
        ]
