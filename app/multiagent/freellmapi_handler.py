"""Message handler that turns queued requests into scoped mini-agent inference."""
from __future__ import annotations

from typing import Any, Mapping

from .freellmapi_client import FreeLLMAPIClient
from .transport import AgentMessage


class FreeLLMAgentHandler:
    """Use FreeLLMAPI for bounded text work without granting tools or side effects."""

    def __init__(
        self,
        client: FreeLLMAPIClient,
        *,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> None:
        if max_tokens < 1 or max_tokens > 8192:
            raise ValueError("max_tokens must be between 1 and 8192")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        self.client = client
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
        result = self.client.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            model=_optional_text(payload.get("model")),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return {
            "success": True,
            "output": result["content"],
            "engine": "freellmapi",
            "model": result["model"],
            "routed_via": result["routed_via"],
            "fallback_attempts": result["fallback_attempts"],
            "usage": result["usage"],
        }


def _safe_text(value: Any, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
