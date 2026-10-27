# -*- coding: utf-8 -*-
"""Coordinate assistant responses and dispatch trusted structured execution requests."""

import logging
from typing import Optional, Dict, Any

from app.core.nexus import nexus, NexusComponent

logger = logging.getLogger(__name__)


class OrchestratorService(NexusComponent):
    """Coordinate input -> assistant -> validated plan or legacy tasks."""

    def __init__(self):
        super().__init__()
        self.assistant = nexus.resolve("assistant_service")
        self.task_runner = nexus.resolve("task_runner")
        self.logger = nexus.resolve("structured_logger")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        if not context or "input_text" not in context:
            return {"success": False, "error": "Input de texto ausente."}
        return self.coordinate_flow(context["input_text"], context=context)

    @staticmethod
    def _response_parts(response: Any) -> tuple[bool, Any, Optional[str]]:
        """Normalize dict and domain Response without guessing at command intent."""
        if isinstance(response, dict):
            return bool(response.get("success", False)), response.get("data", response.get("result", {})), response.get("error")
        success = getattr(response, "success", None)
        if isinstance(success, bool):
            return success, getattr(response, "data", None) or {}, getattr(response, "error", None)
        return False, {}, "invalid_assistant_response"

    def coordinate_flow(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Avoid logging raw user prompts; they may contain secrets or personal data.
        try:
            if self.logger:
                self.logger.execute({"level": "info", "message": "Orchestrating assistant request"})
        except Exception:
            logger.debug("Structured logger unavailable", exc_info=True)

        try:
            assistant_resp = self.assistant.process_command(text)
            ok, data, error = self._response_parts(assistant_resp)
            if not ok:
                return {"success": False, "error": error or "assistant_request_failed"}

            if not isinstance(data, dict):
                return {"success": True, "result": data}

            # Accept only a structured plan explicitly returned by the assistant
            # result; never infer executable steps from natural-language text.
            result_payload = data.get("result", data)
            if not isinstance(result_payload, dict):
                result_payload = {}
            plan = result_payload.get("plan")
            if plan is not None:
                user = "anonymous"
                if context:
                    candidate = context.get("authenticated_user_id")
                    if isinstance(candidate, str) and candidate.strip():
                        user = candidate
                execution = self.task_runner.execute({"plan": plan, "user": user})
                return {
                    "success": bool(execution.get("success", False)) if isinstance(execution, dict) else False,
                    "intent": data.get("intent") or data.get("command_type"),
                    "execution": execution,
                }

            tasks = result_payload.get("tasks", data.get("tasks", []))
            if tasks:
                execution_results = self.task_runner.execute({"tasks": tasks})
                return {
                    "success": bool(execution_results.get("success", False)) if isinstance(execution_results, dict) else False,
                    "intent": data.get("intent") or data.get("command_type"),
                    "execution": execution_results,
                }

            return {"success": True, "result": data}

        except Exception as exc:
            logger.exception("Orchestration failed")
            try:
                if self.logger:
                    self.logger.execute({"level": "error", "message": "Orchestration failed"})
            except Exception:
                logger.debug("Unable to write orchestration error to structured logger", exc_info=True)
            return {"success": False, "error": type(exc).__name__}

    def on_event(self, event_type: str, data: Any) -> None:
        if self.assistant:
            self.assistant.on_event(event_type, data)
        if self.task_runner:
            self.task_runner.on_event(event_type, data)
