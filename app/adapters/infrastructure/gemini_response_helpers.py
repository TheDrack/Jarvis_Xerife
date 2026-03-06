from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Gemini response helper functions.

Module-level utilities for building context messages, mapping function-call
arguments to domain parameters, and converting Gemini function calls into
Intent objects.  These helpers are shared by LLMCommandAdapter and can be
reused by other adapters without importing the full adapter.
"""

import logging
from typing import Optional

from app.domain.models import CommandType, Intent
from app.domain.services.agent_service import AgentService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


def build_context_message(history_provider) -> str:
    """Build context message from the last 3 commands in history.

    Args:
        history_provider: An object with a ``get_recent_history(limit)`` method,
            or ``None`` if history is unavailable.

    Returns:
        Formatted context string or empty string if no history.
    """
    if not history_provider:
        return ""

    try:
        recent_history = history_provider.get_recent_history(limit=3)
        if not recent_history:
            return ""

        context_lines = ["Contexto (últimos comandos executados):"]
        for item in reversed(recent_history):  # Show oldest first
            command_type = item.get("command_type", "unknown")
            user_input = item.get("user_input", "")
            success = item.get("success", False)
            status = "sucesso" if success else "falhou"
            context_lines.append(f"- '{user_input}' -> {command_type} ({status})")

        return "\n".join(context_lines)
    except Exception as e:
        logger.warning(f"Error building context message: {e}")
        return ""


def build_parameters(command_type: CommandType, function_args: dict) -> dict:
    """Build parameters dictionary based on command type and function arguments.

    Args:
        command_type: Type of command.
        function_args: Arguments from function call.

    Returns:
        Dictionary of parameters.
    """
    if command_type == CommandType.TYPE_TEXT:
        return {"text": function_args.get("text", "")}

    elif command_type == CommandType.PRESS_KEY:
        return {"key": function_args.get("key", "")}

    elif command_type == CommandType.OPEN_BROWSER:
        return {}

    elif command_type == CommandType.OPEN_URL:
        url = function_args.get("url", "")
        if url and not url.startswith("http"):
            url = f"https://{url}"
        return {"url": url}

    elif command_type == CommandType.SEARCH_ON_PAGE:
        return {"search_text": function_args.get("search_text", "")}

    elif command_type == CommandType.REPORT_ISSUE:
        return {
            "issue_description": function_args.get("issue_description", ""),
            "context": function_args.get("context", ""),
        }

    return function_args


def convert_function_call_to_intent(function_call, raw_input: str) -> Intent:
    """Convert a Gemini function call to an Intent object.

    Args:
        function_call: The function call from Gemini response.
        raw_input: Original user input.

    Returns:
        Intent object.
    """
    function_name = function_call.name
    function_args = dict(function_call.args) if function_call.args else {}

    command_type = AgentService.map_function_to_command_type(function_name)
    parameters = build_parameters(command_type, function_args)

    logger.info(
        f"LLM function call: {function_name} with args: {function_args} -> {command_type}"
    )

    return Intent(
        command_type=command_type,
        parameters=parameters,
        raw_input=raw_input,
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# NexusComponent wrapper (required by project convention)
# ---------------------------------------------------------------------------


class GeminiResponseHelpers(NexusComponent):
    """Thin NexusComponent wrapper exposing the module-level helper functions."""

    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}
