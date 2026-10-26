"""Bounded declarative tool-plan validation and interpretation.

This module deliberately executes no generated code. Callers inject the registered
handlers and a policy callback; every step is authorized immediately before dispatch.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping


MAX_PLAN_STEPS = 20
MAX_PLAN_BYTES = 64 * 1024
MAX_RESULT_BYTES = 32 * 1024
PLAN_VERSION = "1"


class PlanValidationError(ValueError):
    """Raised when a proposed plan is malformed or exceeds a hard limit."""


@dataclass(frozen=True)
class StepOutcome:
    step_id: str
    tool: str
    status: str
    result: Any = None
    error: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class PlanOutcome:
    execution_id: str
    status: str
    steps: tuple[StepOutcome, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
        }


def validate_plan(plan: Mapping[str, Any], *, max_steps: int = MAX_PLAN_STEPS,
                  max_plan_bytes: int = MAX_PLAN_BYTES) -> dict[str, Any]:
    """Validate a JSON-compatible, strictly shaped plan before any side effect."""
    if not isinstance(plan, Mapping):
        raise PlanValidationError("plan must be an object")
    try:
        encoded = json.dumps(plan, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlanValidationError("plan must contain only finite JSON values") from exc
    if len(encoded) > max_plan_bytes:
        raise PlanValidationError("plan exceeds maximum serialized size")
    if set(plan) != {"version", "execution_id", "steps"}:
        raise PlanValidationError("plan must contain exactly version, execution_id, and steps")
    if plan["version"] != PLAN_VERSION:
        raise PlanValidationError("unsupported plan version")
    execution_id = plan["execution_id"]
    if not isinstance(execution_id, str) or not execution_id.strip() or len(execution_id) > 128:
        raise PlanValidationError("execution_id must be a non-empty string of at most 128 characters")
    steps = plan["steps"]
    if not isinstance(steps, list) or not steps:
        raise PlanValidationError("steps must be a non-empty list")
    if len(steps) > max_steps:
        raise PlanValidationError("plan exceeds maximum step count")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    allowed_step_keys = {"step_id", "tool", "args", "depends_on", "output_fields"}
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping) or set(step) - allowed_step_keys:
            raise PlanValidationError(f"step {index} has an invalid shape")
        if not {"step_id", "tool", "args"}.issubset(step):
            raise PlanValidationError(f"step {index} is missing required fields")
        step_id, tool, args = step["step_id"], step["tool"], step["args"]
        if not isinstance(step_id, str) or not step_id.strip() or len(step_id) > 128:
            raise PlanValidationError(f"step {index} has an invalid step_id")
        if step_id in seen:
            raise PlanValidationError(f"duplicate step_id: {step_id}")
        if not isinstance(tool, str) or not tool.strip() or len(tool) > 200:
            raise PlanValidationError(f"step {step_id} has an invalid tool name")
        if not isinstance(args, Mapping):
            raise PlanValidationError(f"args for step {step_id} must be an object")
        depends_on = step.get("depends_on", [])
        if (not isinstance(depends_on, list) or
                any(not isinstance(dep, str) for dep in depends_on) or
                len(set(depends_on)) != len(depends_on)):
            raise PlanValidationError(f"depends_on for step {step_id} must be a unique list of IDs")
        # This first interpreter is intentionally topological: only earlier steps
        # may be referenced. It does not support loops, recursion, or dynamic branches.
        if any(dep not in seen for dep in depends_on):
            raise PlanValidationError(f"step {step_id} may depend only on earlier steps")
        output_fields = step.get("output_fields")
        if output_fields is not None and (
            not isinstance(output_fields, list)
            or any(not isinstance(field, str) or not field for field in output_fields)
            or len(set(output_fields)) != len(output_fields)
        ):
            raise PlanValidationError(f"output_fields for step {step_id} must be a unique list of strings")
        normalized.append({
            "step_id": step_id,
            "tool": tool,
            "args": dict(args),
            "depends_on": list(depends_on),
            "output_fields": list(output_fields) if output_fields is not None else None,
        })
        seen.add(step_id)
    return {"version": PLAN_VERSION, "execution_id": execution_id, "steps": normalized}


def _resolve_refs(value: Any, results: Mapping[str, Any]) -> Any:
    """Resolve explicit {"$ref": "step_id.path"} references; never evaluate text."""
    if isinstance(value, Mapping):
        if set(value) == {"$ref"}:
            ref = value["$ref"]
            if not isinstance(ref, str) or not ref:
                raise PlanValidationError("$ref must be a non-empty string")
            parts = ref.split(".")
            current = results.get(parts[0], _MISSING)
            for part in parts[1:]:
                if not isinstance(current, Mapping) or part not in current:
                    raise PlanValidationError(f"unavailable result reference: {ref}")
                current = current[part]
            if current is _MISSING:
                raise PlanValidationError(f"unavailable result reference: {ref}")
            return current
        return {key: _resolve_refs(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(item, results) for item in value]
    return value


_MISSING = object()


def _project_result(result: Any, fields: list[str] | None) -> Any:
    """Keep downstream context small; full artifacts should be referenced by URI."""
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PlanValidationError("tool result is not JSON serializable") from exc
    if fields is not None:
        if not isinstance(result, Mapping):
            raise PlanValidationError("output_fields requires an object result")
        missing = [field for field in fields if field not in result]
        if missing:
            raise PlanValidationError("tool result is missing requested output fields")
        result = {field: result[field] for field in fields}
    encoded = json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise PlanValidationError("tool result exceeds maximum projected size")
    return result


class DeclarativePlanInterpreter:
    """Run a validated sequence through an explicit allowlist and policy gate.

    policy(tool, args) returns 'allow', 'approval_required', or 'deny'. The executor
    mapping is trusted host configuration, not data supplied by the plan. Exceptions
    after dispatch are reported as 'unknown' because a side effect may have occurred.
    No retries or implicit approval are performed.
    """

    def __init__(
        self,
        executors: Mapping[str, Callable[[Mapping[str, Any]], Any]],
        policy: Callable[[str, Mapping[str, Any]], str],
        *,
        max_steps: int = MAX_PLAN_STEPS,
        max_plan_bytes: int = MAX_PLAN_BYTES,
    ) -> None:
        self._executors = dict(executors)
        self._policy = policy
        self._max_steps = max_steps
        self._max_plan_bytes = max_plan_bytes

    def execute(self, plan: Mapping[str, Any]) -> PlanOutcome:
        normalized = validate_plan(
            plan, max_steps=self._max_steps, max_plan_bytes=self._max_plan_bytes
        )
        outcomes: list[StepOutcome] = []
        results: dict[str, Any] = {}
        for step in normalized["steps"]:
            step_id, tool = step["step_id"], step["tool"]
            if tool not in self._executors:
                outcomes.append(StepOutcome(step_id, tool, "blocked", error="tool_not_allowlisted"))
                return PlanOutcome(normalized["execution_id"], "blocked", tuple(outcomes))
            try:
                args = _resolve_refs(step["args"], results)
                # Validate resolved arguments too; references must not smuggle
                # non-JSON values into a connector call.
                json.dumps(args, allow_nan=False)
            except (PlanValidationError, TypeError, ValueError) as exc:
                outcomes.append(StepOutcome(step_id, tool, "blocked", error=str(exc)))
                return PlanOutcome(normalized["execution_id"], "blocked", tuple(outcomes))

            decision = self._policy(tool, args)
            if decision == "approval_required":
                outcomes.append(StepOutcome(step_id, tool, "approval_required"))
                return PlanOutcome(normalized["execution_id"], "approval_required", tuple(outcomes))
            if decision != "allow":
                outcomes.append(StepOutcome(step_id, tool, "blocked", error="policy_denied"))
                return PlanOutcome(normalized["execution_id"], "blocked", tuple(outcomes))

            started = time.monotonic()
            try:
                raw_result = self._executors[tool](args)
                projected = _project_result(raw_result, step["output_fields"])
            except Exception as exc:
                duration = int((time.monotonic() - started) * 1000)
                # A connector can fail after an external effect. Do not blindly retry.
                outcomes.append(StepOutcome(step_id, tool, "unknown", error=type(exc).__name__, duration_ms=duration))
                return PlanOutcome(normalized["execution_id"], "unknown", tuple(outcomes))

            outcomes.append(StepOutcome(step_id, tool, "completed", projected,
                                        duration_ms=int((time.monotonic() - started) * 1000)))
            results[step_id] = projected
        return PlanOutcome(normalized["execution_id"], "completed", tuple(outcomes))
