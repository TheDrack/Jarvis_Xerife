"""Runtime invocation, authorization, result, audit, and evidence contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.tools.contracts import ToolManifest

__all__ = [
    "ToolManifest",
    "ToolRequest",
    "ToolResult",
    "ToolAuthorizationDecision",
    "ToolExecutionEvent",
    "EvidenceRecord",
]


class ToolRequest(BaseModel):
    """Invocation envelope. Caller and approval references are untrusted inputs."""

    model_config = ConfigDict(extra="forbid")

    tool_id: str = Field(min_length=3)
    tool_version: Optional[str] = Field(
        default=None, min_length=5, max_length=64
    )
    capability: Optional[str] = Field(default=None, min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    caller: str = Field(
        default="anonymous",
        min_length=1,
        description="Untrusted audit label; never used as authenticated identity.",
    )
    scope: str = Field(default="local", min_length=1)
    approval_id: Optional[str] = Field(
        default=None, min_length=1, max_length=256
    )
    task_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    attempt_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None
    request_id: str = Field(default_factory=lambda: uuid4().hex)


class ToolResult(BaseModel):
    """Stable result envelope returned independently of the underlying adapter."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool_id: str
    request_id: str
    success: bool
    status: str
    output: Any = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: Optional[int] = None
    provider: Optional[str] = None
    tool_version: Optional[str] = None
    retryable: bool = False
    retry_after_seconds: Optional[float] = None
    evidence_refs: list[str] = Field(default_factory=list)


class ToolAuthorizationDecision(BaseModel):
    """Policy decision bound to one authenticated principal and exact tool request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    granted: bool
    principal_id: str = Field(min_length=1, max_length=256)
    session_id: str = Field(min_length=1, max_length=256)
    tool_id: str = Field(min_length=3)
    tool_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    capability: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    approval_id: Optional[str] = None
    correlation_id: Optional[str] = None
    expires_at: datetime

    @model_validator(mode="after")
    def require_timezone(self) -> "ToolAuthorizationDecision":
        if (
            self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
        ):
            raise ValueError("Authorization expiry must be timezone-aware.")
        return self


class ToolExecutionEvent(BaseModel):
    """Secret-free audit metadata for one dispatch attempt."""

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    request_id: str
    correlation_id: Optional[str] = None
    principal_id: Optional[str] = None
    session_id: Optional[str] = None
    approval_id: Optional[str] = None
    tool_id: str
    tool_version: Optional[str] = None
    provider: Optional[str] = None
    request_fingerprint: Optional[str] = None
    cost_units: int = Field(default=1, ge=0)
    caller: str
    scope: str
    status: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    finished_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    latency_ms: int = 0
    error_code: Optional[str] = None


class EvidenceRecord(BaseModel):
    """Provenance envelope for a source artifact or corroborating observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(default_factory=lambda: uuid4().hex)
    source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    uri: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[datetime] = None
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    license: Optional[str] = None
    content_hash: Optional[str] = None
    raw_ref: Optional[str] = None
    transformations: list[str] = Field(default_factory=list)
    corroborates: list[str] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
