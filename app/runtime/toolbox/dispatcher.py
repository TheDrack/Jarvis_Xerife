"""Policy-enforced dispatcher for Nexus-backed tools."""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import inspect
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from jsonschema import Draft202012Validator, ValidationError

from app.runtime.toolbox.contracts import (
    ToolAuthorizationDecision,
    ToolExecutionEvent,
    ToolManifest,
    ToolRequest,
    ToolResult,
)
from app.runtime.toolbox.registry import ToolRegistry

logger = logging.getLogger(__name__)


class _AdapterPreconditionError(RuntimeError):
    """The adapter is installed but its local preconditions are not satisfied."""


class _AdapterOperationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class _ToolRateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: float):
        super().__init__("Limite de chamadas da ferramenta atingido.")
        self.retry_after_seconds = max(0.0, retry_after_seconds)


class _CircuitOpenError(RuntimeError):
    def __init__(self, retry_after_seconds: float):
        super().__init__("Circuit breaker da ferramenta está aberto.")
        self.retry_after_seconds = max(0.0, retry_after_seconds)


class ToolDispatcher:
    """Validates, authorizes, resolves and audits tool calls.

    Process idempotency prevents duplicate calls only for this dispatcher lifetime.
    It is deliberately not represented as durable/provider-side idempotency.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        resolver: Optional[Callable[[str], Any]] = None,
        authorizer: Any = None,
        event_sink: Optional[Callable[[ToolExecutionEvent], None]] = None,
        max_idempotency_entries: int = 10000,
    ) -> None:
        self.registry = registry
        if resolver is None:
            from app.core.nexus import nexus

            resolver = nexus.resolve
        self._resolver = resolver
        self._authorizer = authorizer
        self._event_sink = event_sink
        self._max_idempotency_entries = max(1, int(max_idempotency_entries))
        self._lock = threading.RLock()
        self._inflight: dict[tuple[str, str, str, str, str], str] = {}
        self._completed: dict[
            tuple[str, str, str, str, str], tuple[str, ToolResult]
        ] = {}
        self._rate_calls: dict[str, Any] = {}
        self._breaker_failures: dict[str, int] = {}
        self._breaker_open_until: dict[str, float] = {}

    def dispatch(self, request: ToolRequest | dict) -> ToolResult:
        """Synchronous entry point; use dispatch_async from an active event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.dispatch_async(request))
        raise RuntimeError(
            "Use 'await dispatch_async(...)' dentro de um event loop ativo."
        )

    async def dispatch_async(self, request: ToolRequest | dict) -> ToolResult:
        envelope = (
            request
            if isinstance(request, ToolRequest)
            else ToolRequest.model_validate(request)
        )
        started = time.monotonic()
        started_at = datetime.now(timezone.utc)
        try:
            manifest = self.registry.get(
                envelope.tool_id, envelope.tool_version
            )
        except ValueError as exc:
            return self._finish(
                envelope,
                None,
                started,
                started_at,
                self._failure(
                    envelope,
                    "rejected",
                    "tool_version_required",
                    str(exc),
                ),
            )

        if manifest is None:
            return self._finish(
                envelope,
                None,
                started,
                started_at,
                ToolResult(
                    tool_id=envelope.tool_id,
                    request_id=envelope.request_id,
                    success=False,
                    status="rejected",
                    error_code="tool_not_found",
                    error_message=f"Tool não registrada: {envelope.tool_id}",
                ),
            )
        requested_capability = envelope.capability
        if requested_capability is None and len(manifest.capabilities) == 1:
            requested_capability = manifest.capabilities[0]
        if (
            requested_capability is None
            or requested_capability not in manifest.capabilities
        ):
            return self._finish(
                envelope,
                manifest,
                started,
                started_at,
                self._failure(
                    envelope,
                    "rejected",
                    "capability_not_declared",
                    "A requisição precisa indicar uma capability declarada no manifesto.",
                ),
            )
        if not manifest.enabled:
            return self._finish(
                envelope,
                manifest,
                started,
                started_at,
                self._failure(
                    envelope, "rejected", "tool_disabled", "Tool desabilitada."
                ),
            )
        if not any(
            fnmatch.fnmatchcase(envelope.scope, pattern)
            for pattern in manifest.allowed_scopes
        ):
            return self._finish(
                envelope,
                manifest,
                started,
                started_at,
                self._failure(
                    envelope,
                    "rejected",
                    "scope_denied",
                    "O escopo solicitado não está autorizado para esta ferramenta.",
                ),
            )

        validation_error = self._validate_arguments(
            manifest, envelope.arguments
        )
        if validation_error:
            return self._finish(
                envelope,
                manifest,
                started,
                started_at,
                self._failure(
                    envelope, "rejected", "invalid_arguments", validation_error
                ),
            )

        if manifest.risk_level != "read_only" and not envelope.approval_id:
            return self._finish(
                envelope,
                manifest,
                started,
                started_at,
                self._failure(
                    envelope,
                    "rejected",
                    "approval_reference_required",
                    "Esta ferramenta exige uma referência de aprovação verificável.",
                ),
            )
        if manifest.requires_idempotency_key and not envelope.idempotency_key:
            return self._finish(
                envelope,
                manifest,
                started,
                started_at,
                self._failure(
                    envelope,
                    "rejected",
                    "idempotency_key_required",
                    "Esta ferramenta exige uma idempotency_key.",
                ),
            )

        idempotency_ref = None
        idempotency_digest = None
        idempotency_claimed = False
        operation_started = False
        result: ToolResult
        authorization_decision: Optional[ToolAuthorizationDecision] = None
        try:
            authorizer = self._get_authorizer()
            if authorizer is None or not callable(
                getattr(authorizer, "authorize_tool", None)
            ):
                raise PermissionError(
                    "ToolAuthorizationPolicy confiável indisponível; execução bloqueada."
                )
            decision = authorizer.authorize_tool(envelope, manifest)
            if inspect.isawaitable(decision):
                decision = await decision
            authorization_decision = ToolAuthorizationDecision.model_validate(
                decision
            )
            self._validate_authorization_decision(
                authorization_decision,
                envelope,
                manifest,
                requested_capability,
            )

            # Authorization happens before a cached idempotent result can be
            # returned.
            if (
                envelope.idempotency_key
                and manifest.idempotency_mode == "process"
            ):
                # Idempotency keys belong to an authenticated principal. Keeping
                # the principal in the namespace prevents one tenant from reserving
                # another tenant's key or causing a false cross-tenant conflict.
                idempotency_ref = (
                    authorization_decision.principal_id,
                    manifest.tool_id,
                    manifest.version,
                    requested_capability,
                    envelope.idempotency_key,
                )
                idempotency_digest = self._arguments_digest(
                    envelope.arguments,
                    authorization_decision.principal_id,
                    envelope.scope,
                    envelope.task_id,
                )
                with self._lock:
                    completed = self._completed.get(idempotency_ref)
                    if completed is not None:
                        completed_digest, previous = completed
                        if completed_digest != idempotency_digest:
                            return self._finish(
                                envelope,
                                manifest,
                                started,
                                started_at,
                                self._failure(
                                    envelope,
                                    "rejected",
                                    "idempotency_conflict",
                                    (
                                        "A mesma idempotency_key foi reutilizada com "
                                        "argumentos diferentes."
                                    ),
                                ),
                            )
                        duplicate = previous.model_copy(
                            update={
                                "status": "duplicate",
                                "request_id": envelope.request_id,
                            }
                        )
                        return self._finish(
                            envelope, manifest, started, started_at, duplicate
                        )

                    inflight_digest = self._inflight.get(idempotency_ref)
                    if inflight_digest is not None:
                        if inflight_digest != idempotency_digest:
                            return self._finish(
                                envelope,
                                manifest,
                                started,
                                started_at,
                                self._failure(
                                    envelope,
                                    "rejected",
                                    "idempotency_conflict",
                                    "A idempotency_key já está em uso com argumentos diferentes.",
                                ),
                            )
                        return self._finish(
                            envelope,
                            manifest,
                            started,
                            started_at,
                            self._failure(
                                envelope,
                                "in_progress",
                                "duplicate_in_progress",
                                "Uma execução com esta chave já está em andamento.",
                            ),
                        )
                    self._inflight[idempotency_ref] = idempotency_digest
                    idempotency_claimed = True

            retry_after = self._consume_rate_limit(manifest)
            if retry_after is not None:
                raise _ToolRateLimitError(retry_after)
            breaker_retry_after = self._check_circuit_breaker(manifest)
            if breaker_retry_after is not None:
                raise _CircuitOpenError(breaker_retry_after)

            adapter = self._resolver(manifest.adapter_id)
            if adapter is None or getattr(adapter, "__is_cloud_mock__", False):
                raise _AdapterPreconditionError(
                    f"Adapter indisponível: {manifest.adapter_id}"
                )

            can_execute = getattr(adapter, "can_execute", None)
            if callable(can_execute):
                allowed = can_execute(
                    {
                        "tool_id": manifest.tool_id,
                        "scope": envelope.scope,
                    }
                )
                if inspect.isawaitable(allowed):
                    allowed = await allowed
                if allowed is False:
                    raise _AdapterPreconditionError(
                        "Adapter recusou a pré-condição local de execução."
                    )

            operation = getattr(adapter, manifest.operation, None)
            if not callable(operation):
                raise LookupError(
                    f"Operação '{manifest.operation}' não existe em "
                    f"'{manifest.adapter_id}'."
                )
            operation_started = True
            if inspect.iscoroutinefunction(operation):
                output = await asyncio.wait_for(
                    operation(**envelope.arguments),
                    timeout=manifest.timeout_seconds,
                )
            else:
                output = await asyncio.wait_for(
                    asyncio.to_thread(operation, **envelope.arguments),
                    timeout=manifest.timeout_seconds,
                )
                if inspect.isawaitable(output):
                    output = await asyncio.wait_for(
                        output, timeout=manifest.timeout_seconds
                    )
            if output is None:
                raise _AdapterOperationError(
                    "empty_result",
                    "Adapter retornou resultado vazio; efeito não confirmado.",
                )
            if getattr(output, "status_code", None) == 429:
                headers = getattr(output, "headers", {}) or {}
                try:
                    retry_after = float(headers.get("Retry-After", 1))
                except (TypeError, ValueError):
                    retry_after = 1.0
                raise _ToolRateLimitError(retry_after)
            if getattr(output, "ok", True) is False:
                raise _AdapterOperationError(
                    "provider_rejected", "Provedor recusou a operação."
                )
            if hasattr(output, "json") and callable(output.json):
                output = output.json()
            if isinstance(output, dict) and output.get("ok") is False:
                raise _AdapterOperationError(
                    "provider_rejected", "Provedor recusou a operação."
                )
            if isinstance(output, dict) and output.get("success") is False:
                raise _AdapterOperationError(
                    str(output.get("error_code", "adapter_operation_failed")),
                    "Adapter não confirmou a operação.",
                )
            if manifest.output_schema is not None:
                Draft202012Validator(manifest.output_schema).validate(output)

            result = ToolResult(
                tool_id=manifest.tool_id,
                request_id=envelope.request_id,
                success=True,
                status="succeeded",
                output=output,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except asyncio.CancelledError:
            code = (
                "execution_outcome_unknown"
                if operation_started and manifest.risk_level != "read_only"
                else "execution_cancelled"
            )
            result = self._failure(
                envelope,
                "failed",
                code,
                "Execução cancelada; reconcilie o estado externo antes de tentar novamente.",
            )
        except ValidationError:
            result = self._failure(
                envelope,
                "failed",
                "invalid_output",
                "A saída do adapter não corresponde ao schema declarado.",
            )
        except _ToolRateLimitError as exc:
            result = self._failure(
                envelope,
                "rejected",
                "rate_limited",
                str(exc),
                retryable=True,
                retry_after_seconds=exc.retry_after_seconds,
            )
        except _CircuitOpenError as exc:
            result = self._failure(
                envelope,
                "rejected",
                "circuit_open",
                str(exc),
                retryable=True,
                retry_after_seconds=exc.retry_after_seconds,
            )
        except asyncio.TimeoutError:
            if operation_started and manifest.risk_level != "read_only":
                result = self._failure(
                    envelope,
                    "failed",
                    "execution_outcome_unknown",
                    "Timeout após iniciar efeito externo; reconcilie antes de repetir.",
                )
            else:
                result = self._failure(
                    envelope,
                    "failed",
                    "tool_timeout",
                    "A ferramenta excedeu o timeout configurado.",
                    retryable=manifest.risk_level == "read_only",
                )
        except _AdapterPreconditionError as exc:
            result = self._failure(
                envelope, "failed", "adapter_not_ready", str(exc)
            )
        except _AdapterOperationError as exc:
            result = self._failure(envelope, "failed", exc.code, str(exc))
        except (PermissionError, ValueError) as exc:
            result = self._failure(
                envelope, "rejected", "authorization_denied", str(exc)
            )
        except LookupError as exc:
            result = self._failure(
                envelope, "failed", "operation_not_found", str(exc)
            )
        except Exception as exc:
            logger.warning(
                "Tool dispatch failed for %s (%s)",
                manifest.tool_id,
                type(exc).__name__,
            )
            if operation_started and manifest.risk_level != "read_only":
                result = self._failure(
                    envelope,
                    "failed",
                    "execution_outcome_unknown",
                    "O adapter falhou após iniciar; reconcilie o efeito externo antes de repetir.",
                )
            else:
                retryable = manifest.risk_level == "read_only" and type(
                    exc
                ).__name__ in {
                    "ConnectionError",
                    "Timeout",
                    "ConnectTimeout",
                    "ReadTimeout",
                }
                result = self._failure(
                    envelope,
                    "failed",
                    "execution_failed",
                    f"Falha no adapter ({type(exc).__name__}).",
                    retryable=retryable,
                )
        finally:
            if idempotency_claimed and idempotency_ref is not None:
                with self._lock:
                    # Publish the result and release the in-flight key atomically so
                    # another caller cannot slip into the gap and replay a side
                    # effect.
                    if (
                        idempotency_digest is not None
                        and "result" in locals()
                        and (
                            result.success
                            or (
                                operation_started
                                and manifest.risk_level != "read_only"
                            )
                        )
                    ):
                        self._completed[idempotency_ref] = (
                            idempotency_digest,
                            result,
                        )
                        while (
                            len(self._completed)
                            > self._max_idempotency_entries
                        ):
                            oldest = next(iter(self._completed))
                            self._completed.pop(oldest, None)
                    self._inflight.pop(idempotency_ref, None)

        self._record_circuit_result(manifest, result, operation_started)
        return self._finish(
            envelope,
            manifest,
            started,
            started_at,
            result,
            authorization_decision,
        )

    def _get_authorizer(self) -> Any:
        if self._authorizer is not None:
            return self._authorizer
        # The legacy CapabilityAuthorizer accepts caller-provided identity/boolean
        # confirmation and is deliberately not trusted as an execution policy.
        self._authorizer = self._resolver("tool_authorization_policy")
        if getattr(self._authorizer, "__is_cloud_mock__", False):
            self._authorizer = None
        return self._authorizer

    @staticmethod
    def _validate_authorization_decision(
        decision: ToolAuthorizationDecision,
        request: ToolRequest,
        manifest: ToolManifest,
        requested_capability: str,
    ) -> None:
        expected = {
            "tool_id": manifest.tool_id,
            "tool_version": manifest.version,
            "capability": requested_capability,
            "scope": request.scope,
            "operation": manifest.operation,
            "task_id": request.task_id,
            "attempt_id": request.attempt_id,
        }
        mismatches = [
            field
            for field, value in expected.items()
            if getattr(decision, field) != value
        ]
        if mismatches:
            raise PermissionError(
                "Authorization decision is not bound to this request: "
                + ", ".join(mismatches)
            )
        if not decision.granted:
            raise PermissionError(
                "ToolAuthorizationPolicy denied this request."
            )
        if decision.expires_at <= datetime.now(timezone.utc):
            raise PermissionError("Authorization decision expired.")
        if manifest.risk_level != "read_only":
            if (
                not request.approval_id
                or decision.approval_id != request.approval_id
            ):
                raise PermissionError(
                    "Active tools require a verified, request-bound approval."
                )
        elif (
            decision.approval_id
            and request.approval_id != decision.approval_id
        ):
            raise PermissionError(
                "Approval reference does not match the authorization decision."
            )
        if decision.correlation_id != request.correlation_id:
            raise PermissionError(
                "Authorization decision correlation ID mismatch."
            )

    @staticmethod
    def _arguments_digest(
        arguments: dict[str, Any],
        caller: str,
        scope: str,
        task_id: Optional[str] = None,
    ) -> str:
        canonical = json.dumps(
            {
                "arguments": arguments,
                "caller": caller,
                "scope": scope,
                "task_id": task_id,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_arguments(
        manifest: ToolManifest, arguments: dict[str, Any]
    ) -> Optional[str]:
        errors = sorted(
            Draft202012Validator(manifest.input_schema).iter_errors(arguments),
            key=lambda error: tuple(str(part) for part in error.path),
        )
        if not errors:
            return None
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "arguments"
        return f"{location}: {first.message}"

    def _check_circuit_breaker(
        self, manifest: ToolManifest
    ) -> Optional[float]:
        """Return retry delay when this process has opened the tool circuit."""
        now = time.monotonic()
        with self._lock:
            open_until = self._breaker_open_until.get(manifest.tool_id)
            if open_until is None:
                return None
            if now < open_until:
                return open_until - now
            self._breaker_open_until.pop(manifest.tool_id, None)
            self._breaker_failures[manifest.tool_id] = 0
        return None

    def _record_circuit_result(
        self,
        manifest: ToolManifest,
        result: ToolResult,
        operation_started: bool,
    ) -> None:
        with self._lock:
            if result.success:
                self._breaker_failures.pop(manifest.tool_id, None)
                self._breaker_open_until.pop(manifest.tool_id, None)
                return
            if not operation_started or result.error_code not in {
                "execution_failed",
                "tool_timeout",
                "execution_outcome_unknown",
            }:
                return
            failures = self._breaker_failures.get(manifest.tool_id, 0) + 1
            self._breaker_failures[manifest.tool_id] = failures
            if failures >= manifest.circuit_breaker_threshold:
                self._breaker_open_until[manifest.tool_id] = (
                    time.monotonic() + manifest.circuit_breaker_reset_seconds
                )

    def _consume_rate_limit(self, manifest: ToolManifest) -> Optional[float]:
        """Apply manifest request/window and optional one-second burst budgets."""
        policy = manifest.rate_limit
        if policy is None:
            return None
        now = time.monotonic()
        with self._lock:
            calls = self._rate_calls.setdefault(manifest.tool_id, deque())
            while calls and now - calls[0] >= policy.window_seconds:
                calls.popleft()
            if len(calls) >= policy.requests:
                return max(0.0, policy.window_seconds - (now - calls[0]))
            if policy.burst is not None:
                recent = [
                    timestamp for timestamp in calls if now - timestamp < 1.0
                ]
                if len(recent) >= policy.burst:
                    return max(0.0, 1.0 - (now - recent[0]))
            calls.append(now)
        return None

    @staticmethod
    def _failure(
        request: ToolRequest,
        status: str,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: Optional[float] = None,
    ) -> ToolResult:
        return ToolResult(
            tool_id=request.tool_id,
            request_id=request.request_id,
            success=False,
            status=status,
            error_code=code,
            error_message=message,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
        )

    def _finish(
        self,
        request: ToolRequest,
        manifest: Optional[ToolManifest],
        started: float,
        started_at: Any,
        result: ToolResult,
        authorization_decision: Optional[ToolAuthorizationDecision] = None,
    ) -> ToolResult:
        latency = int((time.monotonic() - started) * 1000)
        updates = {}
        if result.latency_ms is None:
            updates["latency_ms"] = latency
        if manifest is not None:
            if result.provider is None:
                updates["provider"] = manifest.provider
            if result.tool_version is None:
                updates["tool_version"] = manifest.version
        if updates:
            result = result.model_copy(update=updates)
        event = ToolExecutionEvent(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            tool_id=request.tool_id,
            tool_version=manifest.version if manifest else None,
            provider=manifest.provider if manifest else None,
            request_fingerprint=self._arguments_digest(
                request.arguments,
                (
                    authorization_decision.principal_id
                    if authorization_decision
                    else "unauthenticated"
                ),
                request.scope,
                request.task_id,
            ),
            cost_units=manifest.cost_units if manifest else 0,
            caller=(
                authorization_decision.principal_id
                if authorization_decision
                else "unauthenticated"
            ),
            principal_id=(
                authorization_decision.principal_id
                if authorization_decision
                else None
            ),
            session_id=(
                authorization_decision.session_id
                if authorization_decision
                else None
            ),
            approval_id=(
                authorization_decision.approval_id
                if authorization_decision
                else None
            ),
            task_id=request.task_id,
            attempt_id=request.attempt_id,
            scope=request.scope,
            status=result.status,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            latency_ms=latency,
            error_code=result.error_code,
        )
        if self._event_sink:
            try:
                self._event_sink(event)
            except Exception:
                logger.exception(
                    "Tool audit sink failed for %s", request.tool_id
                )
        else:
            logger.info(
                "tool_execution request_id=%s tool_id=%s version=%s status=%s latency_ms=%s",
                event.request_id,
                event.tool_id,
                event.tool_version,
                event.status,
                event.latency_ms,
            )
        return result
