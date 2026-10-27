"""Turn free-form small-model output into a strictly validated declarative plan.

Small local models often wrap JSON in prose or Markdown fences, omit execution_id
or depends_on, write version as the integer 1, or add harmless extra keys. This
module repairs only those structural gaps. It never widens what validate_plan
accepts: the repaired plan is still fully validated, and no tool name, argument
or policy decision is inferred from the model's text.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Mapping

from app.multiagent.execution_plan import (
    PLAN_VERSION,
    PlanValidationError,
    _collect_refs,
    validate_plan,
)

_TOP_LEVEL_KEYS = ("version", "execution_id", "steps")
_STEP_KEYS = ("step_id", "tool", "args", "depends_on", "output_fields")


def _new_execution_id() -> str:
    return uuid.uuid4().hex


def extract_json_object(text: Any) -> dict[str, Any]:
    """Return the first JSON object embedded in model text, ignoring surrounding prose."""
    if not isinstance(text, str) or not text.strip():
        raise PlanValidationError("model output is empty")
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            candidate, _ = decoder.raw_decode(text, start)
        except (json.JSONDecodeError, RecursionError):
            candidate = None
        if isinstance(candidate, dict):
            return candidate
        start = text.find("{", start + 1)
    raise PlanValidationError("model output contains no JSON object")


def repair_model_plan(
    candidate: Mapping[str, Any],
    *,
    new_execution_id: Callable[[], str] = _new_execution_id,
) -> dict[str, Any]:
    """Fill structural gaps in a model-produced plan, then validate it strictly."""
    if not isinstance(candidate, Mapping):
        raise PlanValidationError("plan must be an object")

    plan: dict[str, Any] = {key: candidate[key] for key in _TOP_LEVEL_KEYS if key in candidate}

    version = plan.get("version", PLAN_VERSION)
    if isinstance(version, int) and not isinstance(version, bool) and version == 1:
        version = PLAN_VERSION
    plan["version"] = version

    if not plan.get("execution_id"):
        plan["execution_id"] = new_execution_id()

    steps = plan.get("steps")
    if isinstance(steps, list):
        repaired_steps: list[Any] = []
        earlier: set[str] = set()
        for step in steps:
            if not isinstance(step, Mapping):
                repaired_steps.append(step)  # validate_plan will reject it
                continue
            repaired = {key: step[key] for key in _STEP_KEYS if key in step}
            depends_on = repaired.get("depends_on", [])
            if isinstance(depends_on, list):
                depends_on = list(depends_on)
                args = repaired.get("args")
                if isinstance(args, Mapping):
                    # Declare every reference to an already-earlier step. References to
                    # unknown or later steps stay undeclared, so validation still rejects them.
                    for ref in sorted(_collect_refs(args)):
                        if ref in earlier and ref not in depends_on:
                            depends_on.append(ref)
                repaired["depends_on"] = depends_on
            repaired_steps.append(repaired)
            step_id = repaired.get("step_id")
            if isinstance(step_id, str):
                earlier.add(step_id)
        plan["steps"] = repaired_steps

    return validate_plan(plan)


def parse_model_plan(
    text: Any,
    *,
    new_execution_id: Callable[[], str] = _new_execution_id,
) -> dict[str, Any]:
    """Extract, repair and validate a plan from raw small-model text output."""
    return repair_model_plan(extract_json_object(text), new_execution_id=new_execution_id)
