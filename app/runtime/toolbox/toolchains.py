"""Declarative, typed DAG toolchains built on the common dispatcher."""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Event
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.runtime.toolbox.contracts import ToolRequest, ToolResult


class ToolchainStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    tool_id: str = Field(min_length=3)
    tool_version: Optional[str] = Field(
        default=None, pattern=r"^\d+\.\d+\.\d+$"
    )
    capability: Optional[str] = Field(default=None, min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    arguments: dict[str, Any] = Field(default_factory=dict)
    bindings: dict[str, str] = Field(default_factory=dict)
    max_attempts: int = Field(default=1, ge=1, le=5)
    retry_backoff_seconds: float = Field(default=0.25, ge=0, le=30)


class ToolchainManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    toolchain_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=1)
    steps: list[ToolchainStep] = Field(min_length=1, max_length=100)
    budget_units: int = Field(default=100, ge=0, le=100000)
    continue_on_error: bool = False

    @classmethod
    def from_file(cls, path: str | Path) -> "ToolchainManifest":
        return cls.model_validate(
            json.loads(Path(path).read_text(encoding="utf-8"))
        )

    @model_validator(mode="after")
    def validate_graph(self) -> "ToolchainManifest":
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Toolchain contém step_id duplicado.")
        known = set(step_ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"Step '{
                        step.step_id}' depende de steps inexistentes: {
                        sorted(missing)}")
            if step.step_id in step.depends_on:
                raise ValueError(
                    f"Step '{step.step_id}' não pode depender de si mesmo."
                )
            for argument, reference in step.bindings.items():
                parts = reference.split(".")
                if (
                    len(parts) < 3
                    or parts[0] != "steps"
                    or parts[2] != "output"
                ):
                    raise ValueError(
                        f"Binding '{argument}' inválido. Use steps.<step_id>.output[.<field>]."
                    )
                source_step = parts[1]
                if source_step not in step.depends_on:
                    raise ValueError(
                        f"Binding '{argument}' precisa declarar '{source_step}' em depends_on."
                    )
        self.topological_order()
        return self

    def topological_order(self) -> list[ToolchainStep]:
        """Return a stable topological order or reject a cyclic graph."""
        completed: set[str] = set()
        ordered: list[ToolchainStep] = []
        while len(ordered) < len(self.steps):
            ready = [
                step
                for step in self.steps
                if step.step_id not in completed
                and set(step.depends_on) <= completed
            ]
            if not ready:
                raise ValueError("Toolchain contém dependência cíclica.")
            for step in ready:
                ordered.append(step)
                completed.add(step.step_id)
        return ordered


class ToolchainResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    toolchain_id: str
    success: bool
    status: Literal["succeeded", "partial", "failed", "cancelled"]
    step_results: dict[str, ToolResult] = Field(default_factory=dict)


class ToolchainRunner:
    """Sequential DAG executor with explicit bindings and cancellation checks."""

    def __init__(self, dispatcher: Any, registry: Any = None):
        self.dispatcher = dispatcher
        self.registry = registry or getattr(dispatcher, "registry", None)

    def run_file(self, path: str | Path, **kwargs: Any) -> ToolchainResult:
        return self.run(ToolchainManifest.from_file(path), **kwargs)

    def run(
        self,
        manifest: ToolchainManifest | dict,
        *,
        caller: str = "toolchain_runner",
        scope: str = "local",
        approvals: Optional[dict[str, dict[str, Any]]] = None,
        correlation_id: Optional[str] = None,
        cancel_event: Optional[Event] = None,
    ) -> ToolchainResult:
        chain = (
            manifest
            if isinstance(manifest, ToolchainManifest)
            else ToolchainManifest.model_validate(manifest)
        )
        results: dict[str, ToolResult] = {}
        stopped = False
        cancelled = False
        consumed_budget = 0
        approvals = approvals or {}

        for step in chain.topological_order():
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                stopped = True
            failed_dependencies = [
                dep
                for dep in step.depends_on
                if dep not in results or not results[dep].success
            ]
            if cancelled:
                results[step.step_id] = self._skipped(
                    step.tool_id,
                    "toolchain_cancelled",
                    "Toolchain cancelada antes da execução.",
                )
                continue
            if failed_dependencies:
                results[step.step_id] = self._skipped(
                    step.tool_id,
                    "dependency_failed",
                    f"Dependências não concluídas: {
                        ', '.join(failed_dependencies)}",
                )
                if not chain.continue_on_error:
                    stopped = True
                continue
            if stopped:
                results[step.step_id] = self._skipped(
                    step.tool_id,
                    "toolchain_stopped",
                    "Execução interrompida após falha anterior.",
                )
                continue

            try:
                tool_manifest = (
                    self.registry.get(step.tool_id, step.tool_version)
                    if self.registry is not None
                    else None
                )
            except ValueError as exc:
                results[step.step_id] = self._skipped(
                    step.tool_id, "tool_version_required", str(exc)
                )
                stopped = not chain.continue_on_error
                continue
            cost_units = (
                tool_manifest.cost_units if tool_manifest is not None else 1
            )
            if consumed_budget + cost_units > chain.budget_units:
                results[step.step_id] = self._skipped(
                    step.tool_id,
                    "budget_exceeded",
                    "A toolchain excederia o orçamento de execução configurado.",
                )
                stopped = True
                continue

            result = None
            for attempt in range(1, step.max_attempts + 1):
                if consumed_budget + cost_units > chain.budget_units:
                    result = self._skipped(
                        step.tool_id,
                        "budget_exceeded",
                        "Orçamento esgotado antes da próxima tentativa.",
                    )
                    stopped = True
                    break
                consumed_budget += cost_units
                try:
                    arguments = dict(step.arguments)
                    for argument, reference in step.bindings.items():
                        arguments[argument] = self._resolve_binding(
                            reference, results
                        )
                    approval = approvals.get(step.step_id, {})
                    request = ToolRequest(
                        tool_id=step.tool_id,
                        tool_version=step.tool_version,
                        capability=step.capability,
                        arguments=arguments,
                        caller=caller,
                        scope=scope,
                        approval_id=approval.get("approval_id"),
                        idempotency_key=approval.get("idempotency_key"),
                        correlation_id=correlation_id,
                    )
                    result = self.dispatcher.dispatch(request)
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    result = self._skipped(
                        step.tool_id, "binding_error", str(exc)
                    )

                may_retry = (
                    result.retryable
                    and tool_manifest is not None
                    and tool_manifest.risk_level == "read_only"
                    and attempt < step.max_attempts
                )
                if not may_retry:
                    break
                delay = max(
                    step.retry_backoff_seconds * attempt,
                    result.retry_after_seconds or 0.0,
                )
                if cancel_event is not None:
                    if cancel_event.wait(delay):
                        cancelled = True
                        result = self._skipped(
                            step.tool_id,
                            "toolchain_cancelled",
                            "Toolchain cancelada durante o backoff de retry.",
                        )
                        break
                elif delay:
                    time.sleep(delay)

            if result is None:
                result = self._skipped(
                    step.tool_id,
                    "toolchain_stopped",
                    "Etapa não foi executada.",
                )
            results[step.step_id] = result
            if not result.success and not chain.continue_on_error:
                stopped = True

        succeeded = sum(1 for result in results.values() if result.success)
        failed = len(results) - succeeded
        if cancelled:
            status = "cancelled"
        elif failed == 0:
            status = "succeeded"
        elif succeeded:
            status = "partial"
        else:
            status = "failed"
        return ToolchainResult(
            toolchain_id=chain.toolchain_id,
            success=status == "succeeded",
            status=status,
            step_results=results,
        )

    @staticmethod
    def _resolve_binding(
        reference: str, results: dict[str, ToolResult]
    ) -> Any:
        parts = reference.split(".")
        source_step = parts[1]
        if source_step not in results or not results[source_step].success:
            raise ValueError(
                f"Resultado de origem indisponível: {source_step}"
            )
        value: Any = results[source_step].output
        for part in parts[3:]:
            if isinstance(value, dict):
                value = value[part]
            elif isinstance(value, list):
                value = value[int(part)]
            else:
                raise TypeError(
                    f"Binding não pode navegar em {type(value).__name__}."
                )
        return value

    @staticmethod
    def _skipped(tool_id: str, code: str, message: str) -> ToolResult:
        return ToolResult(
            tool_id=tool_id,
            request_id="",
            success=False,
            status="rejected",
            error_code=code,
            error_message=message,
        )
