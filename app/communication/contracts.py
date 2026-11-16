"""Provider-neutral contracts for capturing and replaying communications."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class CommunicationRequest(BaseModel):
    """One logical operation; credentials must be injected at execution time."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    adapter_id: str = Field(min_length=3, max_length=128)
    protocol: str = Field(min_length=1, max_length=64)
    operation: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, max_length=128)


class CommunicationCaptureRecord(BaseModel):
    """Persisted, secret-redacted operation template and outcome metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    capture_id: str = Field(default_factory=lambda: uuid4().hex)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request: dict[str, Any]
    response: Any = None
