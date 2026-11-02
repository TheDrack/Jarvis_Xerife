"""Message handler that uses the provider-neutral model runtime port."""

from __future__ import annotations

from typing import Any, Mapping

from app.application.ports.model_runtime import (
    ModelInvocationRequest,
    ModelMessage,
    ModelRuntime,
)
from .transport import AgentMessage


class FreeLLMAgentHandler:
    """Use a bounded text model runtime without granting tools or side effects."""

    def __init__(
        self,
        runtime: ModelRuntime,
        *,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> None:
        if not isinstance(runtime, ModelRuntime):
            raise TypeError("runtime must implement the ModelRuntime protocol")
        if max_tokens < 1 or max_tokens > 8192:
            raise ValueError("max_tokens must be between 1 and 8192")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        self.runtime = runtime
        self.max_tokens = max_tokens
        self.temperature = temperature

    def __call__(self, message: AgentMessage) -> Mapping[str, Any]:
        if message.kind != "request":
            return {"success": False, "error": "unsupported_message_kind"}
        payload = message.payload
        objective = payload.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            return {"success": False, "error": "missing_objective"}

        task_type = _safe_text(payload.get("task_type"), "general")
        constraints = _safe_list(payload.get("constraints"))
        acceptance = _safe_list(payload.get("acceptance_criteria"))
        context = _safe_text(payload.get("context"), "")
        system = (
            "You are a scoped Jarvis mini-agent. Perform text analysis only. "
            "You have no tool execution, browser, filesystem, or external-action access. "
            "Never claim you ran commands, inspected files, searched the web, or changed systems "
            "unless that evidence is included in the supplied context. Be explicit about uncertainty. "
            "Return a concise, useful result and follow the acceptance criteria."
        )
        user_parts = [
            f"Task type: {task_type}",
            f"Objective:\n{objective.strip()}",
        ]
        if constraints:
            user_parts.append("Constraints:\n" + "\n".join(f"- {item}" for item in constraints))
        if acceptance:
            user_parts.append(
                "Acceptance criteria:\n" + "\n".join(f"- {item}" for item in acceptance)
            )
        if context:
            user_parts.append("Provided context (unverified input):\n" + context)

        result = self.runtime.invoke(
            ModelInvocationRequest(
                messages=(
                    ModelMessage(role="system", content=system),
                    ModelMessage(role="user", content="\n\n".join(user_parts)),
                ),
                model_id=_optional_text(payload.get("model")),
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            )
        )
        return {
            "success": True,
            "output": result.content,
            "engine": "freellmapi",
            "provider": result.provider_id,
            "model": result.model_id,
            "routed_via": result.routed_via,
            "fallback_attempts": result.fallback_attempts,
            "usage": result.usage.to_dict(),
        }


def _safe_text(value: Any, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
