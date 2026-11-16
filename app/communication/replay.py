"""Explicitly authorized replay of captured communication templates."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.communication.capture import (
    CommunicationCapture,
    _is_secret_key,
    redact_secrets,
)
from app.communication.contracts import CommunicationRequest
from app.communication.registry import CommunicationRegistry


class CommunicationReplay:
    """Replay a captured operation; a capture is not permission to repeat it."""

    def __init__(
        self,
        capture: CommunicationCapture,
        registry: CommunicationRegistry,
        *,
        authorizer: Callable[[Any, dict[str, Any], dict[str, Any], str | None], bool]
        | None = None,
    ) -> None:
        self._capture = capture
        self._registry = registry
        self._authorizer = authorizer

    def execute(
        self,
        capture_id: str,
        *,
        overrides: Mapping[str, Any] | None = None,
        runtime_context: Mapping[str, Any] | None = None,
        approval_ref: str | None = None,
    ) -> Any:
        record = self._capture.get(capture_id)
        request = CommunicationRequest.model_validate(record.request)
        payload = request.payload
        replay_payload = dict(payload)
        if overrides:
            if any(_is_secret_key(key) for key in overrides):
                raise ValueError(
                    "credentials must be supplied through the authorized runtime context"
                )
            replay_payload.update(dict(overrides))
        safe_payload = redact_secrets(replay_payload)
        context = dict(runtime_context or {})
        safe_context = redact_secrets(context)
        if self._authorizer is None or not self._authorizer(
            record, safe_payload, safe_context, approval_ref
        ):
            raise PermissionError("communication replay is not authorized")
        adapter = self._registry.resolve(request.adapter_id)
        context.update({"replay": True, "capture_id": record.capture_id})
        return adapter.execute(request.operation, replay_payload, context=context)
