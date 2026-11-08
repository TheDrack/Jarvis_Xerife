"""Fail-closed host policy for trusted tool execution.

The policy deliberately receives identity, task ownership, executor leases, and
approval evidence from injected host-owned resolvers. None of these values are
derived from ToolRequest.caller or other request-supplied identity labels.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from app.runtime.toolbox.contracts import (
    ToolAuthorizationDecision,
    ToolManifest,
    ToolRequest,
)


@dataclass(frozen=True)
class TrustedToolPrincipal:
    """Authenticated principal resolved by the host, never from a tool request."""

    principal_id: str
    session_id: str
    capabilities: frozenset[str]
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if not self.principal_id.strip() or len(self.principal_id) > 256:
            raise ValueError("principal_id must contain 1 to 256 characters")
        if not self.session_id.strip() or len(self.session_id) > 256:
            raise ValueError("session_id must contain 1 to 256 characters")
        if any(not item.strip() for item in self.capabilities):
            raise ValueError("capability grants must not contain empty values")
        if self.agent_id is not None and (
            not self.agent_id.strip() or len(self.agent_id) > 200
        ):
            raise ValueError("agent_id must contain 1 to 200 characters")


@dataclass(frozen=True)
class VerifiedToolApproval:
    """Approval record returned only by a trusted, durable approval verifier."""

    approval_id: str
    status: str
    principal_id: str
    session_id: str
    task_id: str | None
    tool_id: str
    tool_version: str
    capability: str
    scope: str
    operation: str
    arguments_digest: str
    approved_at: datetime
    expires_at: datetime


def tool_request_digest(request: ToolRequest) -> str:
    """Hash canonical request intent to prevent approval replay with altered input."""
    canonical = json.dumps(
        {
            "tool_id": request.tool_id,
            "tool_version": request.tool_version,
            "capability": request.capability,
            "arguments": request.arguments,
            "scope": request.scope,
            "task_id": request.task_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class HostToolAuthorizationPolicy:
    """Resolve host identity and enforce capability, task, executor and approval gates.

    Required resolvers are intentionally injected at the composition root:
    - principal_resolver: current authenticated principal/session and server grants;
    - task_owner_resolver: persisted owner for a task;
    - task_executor_resolver: active attempt's persisted worker identity;
    - approval_verifier: durable approval lookup with revocation/expiry semantics.

    Missing evidence is a denial. This class does not silently fall back to
    caller labels, user metadata, booleans, or an in-memory approval cache.
    """

    def __init__(
        self,
        *,
        principal_resolver: Callable[[], TrustedToolPrincipal | Mapping[str, Any] | None],
        task_owner_resolver: Callable[[str], str | None] | None = None,
        task_executor_resolver: Callable[[str, str], str | None] | None = None,
        approval_verifier: Callable[[str], VerifiedToolApproval | Mapping[str, Any] | None] | None = None,
        clock: Callable[[], datetime] | None = None,
        decision_ttl: timedelta = timedelta(seconds=60),
    ) -> None:
        if decision_ttl <= timedelta(0) or decision_ttl > timedelta(minutes=5):
            raise ValueError("decision_ttl must be greater than zero and at most five minutes")
        self._principal_resolver = principal_resolver
        self._task_owner_resolver = task_owner_resolver
        self._task_executor_resolver = task_executor_resolver
        self._approval_verifier = approval_verifier
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._decision_ttl = decision_ttl

    def authorize_tool(
        self,
        request: ToolRequest,
        manifest: ToolManifest,
    ) -> ToolAuthorizationDecision:
        principal = self._resolve_principal()
        capability = request.capability or (
            manifest.capabilities[0] if len(manifest.capabilities) == 1 else None
        )
        if not capability or capability not in manifest.capabilities:
            raise PermissionError("Requested capability is not declared by the tool manifest")
        if capability not in principal.capabilities:
            raise PermissionError("Authenticated principal has no server-side capability grant")
        if not any(
            fnmatch.fnmatchcase(request.scope, pattern)
            for pattern in manifest.allowed_scopes
        ):
            raise PermissionError("Requested scope is outside the tool manifest allowlist")

        self._verify_task_binding(request, principal)

        approval_id = None
        expires_at = self._now() + self._decision_ttl
        if manifest.risk_level != "read_only":
            approval = self._verify_approval(request, manifest, principal, capability)
            approval_id = approval.approval_id
            expires_at = approval.expires_at

        return ToolAuthorizationDecision(
            granted=True,
            principal_id=principal.principal_id,
            session_id=principal.session_id,
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            capability=capability,
            scope=request.scope,
            operation=manifest.operation,
            task_id=request.task_id,
            attempt_id=request.attempt_id,
            approval_id=approval_id,
            correlation_id=request.correlation_id,
            expires_at=expires_at,
        )

    def _resolve_principal(self) -> TrustedToolPrincipal:
        try:
            value = self._principal_resolver()
        except Exception as exc:
            raise PermissionError(
                f"Trusted principal resolution failed ({type(exc).__name__})"
            ) from None
        if value is None:
            raise PermissionError("No authenticated principal is available")
        if isinstance(value, TrustedToolPrincipal):
            return value
        if isinstance(value, Mapping):
            try:
                capabilities = value.get("capabilities", ())
                if not isinstance(capabilities, (list, tuple, set, frozenset)):
                    raise ValueError("capabilities must be a collection")
                return TrustedToolPrincipal(
                    principal_id=str(value.get("principal_id") or ""),
                    session_id=str(value.get("session_id") or ""),
                    capabilities=frozenset(str(item) for item in capabilities),
                    agent_id=(
                        str(value["agent_id"])
                        if value.get("agent_id") is not None
                        else None
                    ),
                )
            except (TypeError, ValueError) as exc:
                raise PermissionError("Trusted principal context is invalid") from exc
        raise PermissionError("Principal resolver returned an unsupported identity type")

    def _verify_task_binding(self, request: ToolRequest, principal: TrustedToolPrincipal) -> None:
        if request.attempt_id and not request.task_id:
            raise PermissionError("An attempt must be bound to a task")
        if principal.agent_id and (not request.task_id or not request.attempt_id):
            raise PermissionError("Worker tool execution requires a task and attempt binding")
        if not request.task_id:
            return
        if self._task_owner_resolver is None:
            raise PermissionError("Trusted task-owner resolver is unavailable")
        try:
            owner_id = self._task_owner_resolver(request.task_id)
        except Exception as exc:
            raise PermissionError(
                f"Task ownership verification failed ({type(exc).__name__})"
            ) from None
        if owner_id != principal.principal_id:
            raise PermissionError("Task is not owned by the authenticated principal")
        if principal.agent_id:
            if self._task_executor_resolver is None:
                raise PermissionError("Trusted task-executor resolver is unavailable")
            try:
                executor_id = self._task_executor_resolver(
                    request.task_id, request.attempt_id or ""
                )
            except Exception as exc:
                raise PermissionError(
                    f"Task executor verification failed ({type(exc).__name__})"
                ) from None
            if executor_id != principal.agent_id:
                raise PermissionError("Worker does not own the active task attempt")

    def _verify_approval(
        self,
        request: ToolRequest,
        manifest: ToolManifest,
        principal: TrustedToolPrincipal,
        capability: str,
    ) -> VerifiedToolApproval:
        if not request.approval_id:
            raise PermissionError("Active tool execution requires an approval reference")
        if self._approval_verifier is None:
            raise PermissionError("Trusted approval verifier is unavailable")
        try:
            value = self._approval_verifier(request.approval_id)
        except Exception as exc:
            raise PermissionError(
                f"Approval verification failed ({type(exc).__name__})"
            ) from None
        if value is None:
            raise PermissionError("Approval does not exist, is revoked, or is unavailable")
        if isinstance(value, VerifiedToolApproval):
            approval = value
        elif isinstance(value, Mapping):
            try:
                approval = VerifiedToolApproval(**dict(value))
            except (TypeError, ValueError) as exc:
                raise PermissionError("Approval record is invalid") from exc
        else:
            raise PermissionError("Approval verifier returned an unsupported record")

        expected = {
            "approval_id": request.approval_id,
            "status": "approved",
            "principal_id": principal.principal_id,
            "session_id": principal.session_id,
            "task_id": request.task_id,
            "tool_id": manifest.tool_id,
            "tool_version": manifest.version,
            "capability": capability,
            "scope": request.scope,
            "operation": manifest.operation,
            "arguments_digest": tool_request_digest(request),
        }
        mismatches = [
            name for name, expected_value in expected.items()
            if getattr(approval, name) != expected_value
        ]
        if mismatches:
            raise PermissionError(
                "Approval does not match this exact request: " + ", ".join(mismatches)
            )
        now = self._now()
        if (
            approval.approved_at.tzinfo is None
            or approval.approved_at.utcoffset() is None
            or approval.expires_at.tzinfo is None
            or approval.expires_at.utcoffset() is None
        ):
            raise PermissionError("Approval timestamps must be timezone-aware")
        if approval.approved_at > now or approval.expires_at <= now:
            raise PermissionError("Approval is not currently valid")
        return approval

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise PermissionError("Authorization clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)
