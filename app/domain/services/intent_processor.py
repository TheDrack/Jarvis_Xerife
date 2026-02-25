from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Intent Processor - Pure business logic for processing intents"""

from datetime import datetime
from typing import Optional

from app.domain.models import Command, CommandType, Intent, Response


class IntentProcessor(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """
    Processes intents and creates commands.
    Pure Python, no dependencies on hardware or frameworks.
    """

    def create_command(self, intent: Intent, context: Optional[dict] = None) -> Command:
        """
        Create a Command from an Intent

        Args:
            intent: The intent to process
            context: Optional context information

        Returns:
            Command object ready for execution
        """
        return Command(
            intent=intent,
            timestamp=datetime.now().isoformat(),
            context=context or {},
        )

    def validate_intent(self, intent: Intent) -> Response:
        """
        Validate an intent before processing

        Args:
            intent: Intent to validate

        Returns:
            Response indicating validation result
        """
        # Check for unknown commands
        if intent.command_type == CommandType.UNKNOWN:
            return Response(
                success=False,
                message=f"Unknown command: {intent.raw_input}",
                error="UNKNOWN_COMMAND",
            )

        # Validate required parameters based on command type
        validation_result = self._validate_parameters(intent)
        if not validation_result.success:
            return validation_result

        return Response(success=True, message="Intent is valid")

    def _validate_parameters(self, intent: Intent) -> Response:
        """
        Validate parameters for specific command types

        Args:
            intent: Intent to validate

        Returns:
            Response indicating validation result
        """
        if intent.command_type == CommandType.TYPE_TEXT:
            if not intent.parameters.get("text"):
                return Response(
                    success=False,
                    message="Text parameter is required for type command",
                    error="MISSING_PARAMETER",
                )

        elif intent.command_type == CommandType.PRESS_KEY:
            if not intent.parameters.get("key"):
                return Response(
                    success=False,
                    message="Key parameter is required for press command",
                    error="MISSING_PARAMETER",
                )

        elif intent.command_type == CommandType.OPEN_URL:
            if not intent.parameters.get("url"):
                return Response(
                    success=False,
                    message="URL parameter is required for open URL command",
                    error="MISSING_PARAMETER",
                )

        elif intent.command_type == CommandType.SEARCH_ON_PAGE:
            if not intent.parameters.get("search_text"):
                return Response(
                    success=False,
                    message="Search text parameter is required",
                    error="MISSING_PARAMETER",
                )

        return Response(success=True, message="Parameters are valid")

    def should_provide_feedback(self, command_type: CommandType) -> bool:
        """
        Determine if voice feedback should be provided for a command

        Args:
            command_type: Type of command

        Returns:
            True if voice feedback should be provided
        """
        # Some commands might not need voice feedback
        silent_commands = {CommandType.TYPE_TEXT, CommandType.PRESS_KEY}
        return command_type not in silent_commands
