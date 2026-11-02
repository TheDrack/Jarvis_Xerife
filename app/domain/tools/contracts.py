"""Typed, provider-neutral contracts for the Universal Tool Registry.

This first increment defines immutable manifest metadata only. It deliberately
does not execute adapters, resolve credentials, probe health, or authorize calls.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_TOOL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)
_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[.:_-][a-z0-9]+)*$")
_CREDENTIAL_REF_PATTERN = re.compile(
    r"^(?:secret|env|vault)://[A-Za-z0-9][A-Za-z0-9._/-]*$"
)


class HealthPolicy(BaseModel):
    """Declarative health-check policy; this model does not perform a probe."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["none", "on_demand", "periodic"] = "on_demand"
    interval_seconds: int | None = Field(default=None, ge=1, le=86400)
    failure_threshold: int = Field(default=3, ge=1, le=100)
    cooldown_seconds: float = Field(default=30.0, gt=0, le=86400, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_periodic_interval(self) -> "HealthPolicy":
        if self.mode == "periodic" and self.interval_seconds is None:
            raise ValueError("periodic health policy requires interval_seconds")
        return self


class RateLimitPolicy(BaseModel):
    """Declarative request-rate budget for a future dispatcher."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests: int = Field(gt=0)
    window_seconds: int = Field(gt=0)
    burst: int | None = Field(default=None, gt=0)


class ToolManifest(BaseModel):
    """Versioned metadata describing one atomic tool implementation.

    A manifest is descriptive metadata, not an executable capability grant.
    The registry stores snapshots and requires exact version resolution.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    tool_id: str = Field(min_length=3, max_length=128)
    version: str = Field(min_length=5, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    adapter_id: str = Field(min_length=3, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=128)

    capabilities: tuple[str, ...] = Field(min_length=1)
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    )
    output_schema: dict[str, Any] = Field(
        default_factory=lambda: {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    )

    dependencies: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    execution_mode: Literal["read_only", "active_bounded", "intervention"] = "read_only"
    trust_level: Literal["untrusted", "community", "trusted", "system"] = "untrusted"
    data_classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    side_effects: tuple[str, ...] = ()

    credential_refs: tuple[str, ...] = ()
    health_policy: HealthPolicy = Field(default_factory=HealthPolicy)
    rate_limit: RateLimitPolicy | None = None
    cost_limit_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300, allow_inf_nan=False)
    idempotency: Literal["required", "supported", "not_applicable"] = "required"

    license: str | None = Field(default=None, min_length=1, max_length=128)
    terms_uri: str | None = Field(default=None, min_length=8, max_length=2048)

    @field_validator("tool_id", "adapter_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        if not _TOOL_ID_PATTERN.fullmatch(value):
            raise ValueError("identifier must use lowercase dot/underscore/hyphen segments")
        return value

    @field_validator("version")
    @classmethod
    def validate_semver(cls, value: str) -> str:
        if not _SEMVER_PATTERN.fullmatch(value):
            raise ValueError("version must follow semantic versioning (MAJOR.MINOR.PATCH)")
        return value

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("at least one capability is required")
        if any(not _PERMISSION_PATTERN.fullmatch(value) for value in values):
            raise ValueError("capabilities must be lowercase capability identifiers")
        if len(set(values)) != len(values):
            raise ValueError("capabilities must not contain duplicates")
        return values

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _TOOL_ID_PATTERN.fullmatch(value) for value in values):
            raise ValueError("dependencies must contain valid tool identifiers")
        if len(set(values)) != len(values):
            raise ValueError("dependencies must not contain duplicates")
        return values

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _PERMISSION_PATTERN.fullmatch(value) for value in values):
            raise ValueError("permissions must contain lowercase permission identifiers")
        if len(set(values)) != len(values):
            raise ValueError("permissions must not contain duplicates")
        return values

    @field_validator("credential_refs")
    @classmethod
    def validate_credential_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _CREDENTIAL_REF_PATTERN.fullmatch(value) for value in values):
            raise ValueError(
                "credentials must be references using secret://, env://, or vault://; "
                "raw credential values are forbidden"
            )
        if len(set(values)) != len(values):
            raise ValueError("credential references must not contain duplicates")
        return values

    @field_validator("side_effects")
    @classmethod
    def validate_side_effects(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() for value in values):
            raise ValueError("side_effects entries must not be empty")
        if len(set(values)) != len(values):
            raise ValueError("side_effects must not contain duplicates")
        return values

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_object_schema_shape(cls, schema: dict[str, Any]) -> dict[str, Any]:
        """Validate the manifest's object-schema envelope, not full JSON Schema semantics."""
        if schema.get("type") != "object":
            raise ValueError("tool input/output schemas must declare an object root")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("schema properties must be an object")
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
            raise ValueError("schema required must be a list of strings")
        if len(set(required)) != len(required):
            raise ValueError("schema required entries must not contain duplicates")
        additional = schema.get("additionalProperties", False)
        if not isinstance(additional, (bool, dict)):
            raise ValueError("additionalProperties must be a boolean or schema object")
        return schema

    @field_validator("terms_uri")
    @classmethod
    def validate_terms_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("terms_uri must be an absolute HTTP or HTTPS URL")
        return value

    @model_validator(mode="after")
    def validate_execution_declaration(self) -> "ToolManifest":
        if self.execution_mode == "read_only" and self.side_effects:
            raise ValueError("read_only tools cannot declare side effects")
        if self.execution_mode != "read_only" and not self.permissions:
            raise ValueError("active or intervention tools must declare permissions")
        return self
