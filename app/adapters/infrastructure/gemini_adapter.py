from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Gemini LLM Adapter - Google Generative AI integration for command interpretation

Note: This adapter uses the new google-genai library.
The library uses the latest Google Generative AI API.
Default model is 'gemini-flash-latest' for improved performance.
"""

import asyncio
import logging
import os
from typing import Optional

from google import genai

from app.adapters.infrastructure.gemini_response_helpers import (
    build_context_message,
    convert_function_call_to_intent,
)
from app.adapters.infrastructure.github_issue_mixin import GitHubIssueMixin
from app.application.ports import VoiceProvider
from app.domain.models import CommandType, Intent
from app.domain.services.agent_service import AgentService

logger = logging.getLogger(__name__)


class LLMCommandAdapter(GitHubIssueMixin):
    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    """
    Adapter that uses Google Gemini API to interpret commands using Function Calling.
    Converts AI responses into Intent objects that IntentProcessor understands.
    Uses AsyncIO to avoid blocking the voice loop.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-flash-latest",
        voice_provider: Optional[VoiceProvider] = None,
        wake_word: str = "xerife",
        history_provider: Optional["HistoryProvider"] = None,
    ):
        """
        Initialize the LLM Command Adapter

        Args:
            api_key: Google Gemini API key (defaults to GEMINI_API_KEY env var)
            model_name: Name of the Gemini model to use
            voice_provider: Optional voice provider for clarifications
            wake_word: The wake word to filter out from commands
            history_provider: Optional history provider for context
        """
        self.wake_word = wake_word
        self.voice_provider = voice_provider
        self.history_provider = history_provider
        self.model_name = model_name

        # Get API key from parameter or environment
        # Support both GOOGLE_API_KEY and GEMINI_API_KEY for compatibility
        self.api_key = (
            api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY or GEMINI_API_KEY must be provided or set in environment variables"
            )

        # Initialize the new Gemini client
        try:
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise ValueError(f"Failed to initialize Gemini client: {e}")

        # Get function declarations from AgentService
        self.functions = AgentService.get_function_declarations()
        self.system_instruction = AgentService.get_system_instruction()

        # Store chat history for conversational context
        self.chat_history = []

        logger.info(f"Initialized LLMCommandAdapter with model {self.model_name}")

    def interpret(self, raw_input: str) -> Intent:
        """
        Interpret a raw text command into a structured Intent using asyncio.
        This is a synchronous wrapper around the async interpretation.

        Args:
            raw_input: Raw text from voice or text input

        Returns:
            Intent object with command type and parameters
        """
        # Run async interpretation in event loop
        try:
            # If there's a running event loop, avoid nested loop issues
            asyncio.get_running_loop()
            logger.warning("Event loop already running, using sync fallback")
            return self._interpret_sync(raw_input)
        except RuntimeError:
            # No running event loop in this thread; safe to create one
            return asyncio.run(self.interpret_async(raw_input))

    async def interpret_async(self, raw_input: str) -> Intent:
        """
        Async interpretation of raw text command into a structured Intent.

        Args:
            raw_input: Raw text from voice or text input

        Returns:
            Intent object with command type and parameters
        """
        # Normalize input
        command = raw_input.lower().strip()

        # Remove wake word if present
        if self.wake_word in command:
            command = command.replace(self.wake_word, "").strip()

        if not command:
            return Intent(
                command_type=CommandType.UNKNOWN,
                parameters={"raw_command": command},
                raw_input=raw_input,
                confidence=0.0,
            )

        try:
            # Add context from recent history if available
            context_message = self._build_context_message()
            full_message = (
                f"{context_message}\n\n{command}" if context_message else command
            )

            # Build tools for function calling
            tools = [genai.types.Tool(function_declarations=self.functions)]

            # Send message to Gemini using the new client API
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=full_message,
                config=genai.types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    tools=tools,
                ),
            )

            # Check if the model used a function call
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        # Check for function call
                        if hasattr(part, "function_call") and part.function_call:
                            return self._convert_function_call_to_intent(
                                part.function_call, raw_input
                            )

                        # Check for text response (model asking for clarification)
                        elif hasattr(part, "text") and part.text:
                            # Model is asking for clarification
                            self._ask_for_clarification(part.text)
                            return Intent(
                                command_type=CommandType.UNKNOWN,
                                parameters={
                                    "raw_command": command,
                                    "clarification": part.text,
                                },
                                raw_input=raw_input,
                                confidence=0.3,
                            )

            # No function call or text, treat as unknown
            logger.warning(f"No function call or text in response for: {command}")
            return Intent(
                command_type=CommandType.UNKNOWN,
                parameters={"raw_command": command},
                raw_input=raw_input,
                confidence=0.5,
            )

        except Exception as e:
            # Check if this is a 503 error from Google Gemini API
            error_str = str(e)
            is_503_error = False

            # Check for 503 status code or UNAVAILABLE in the error message
            if "503" in error_str or "UNAVAILABLE" in error_str.upper():
                is_503_error = True

            if is_503_error:
                # Log as INFRA_FAILURE
                logger.error(
                    f"INFRA_FAILURE: Gemini API returned 503 (UNAVAILABLE) - {error_str}",
                    exc_info=True,
                )

                # Create GitHub issue asynchronously
                try:
                    await self._create_github_issue_for_infra_failure(
                        e, f"Gemini API Error: {error_str}\nCommand: {command}"
                    )
                except Exception as issue_error:
                    logger.error(
                        f"Failed to create GitHub issue for 503 error: {issue_error}"
                    )
            else:
                logger.error(f"Error during LLM interpretation: {e}", exc_info=True)

            return Intent(
                command_type=CommandType.UNKNOWN,
                parameters={"raw_command": command, "error": str(e)},
                raw_input=raw_input,
                confidence=0.0,
            )

    def _interpret_sync(self, raw_input: str) -> Intent:
        """
        Synchronous fallback for interpretation when async is not available.

        Args:
            raw_input: Raw text from voice or text input

        Returns:
            Intent object with command type and parameters
        """
        # Normalize input
        command = raw_input.lower().strip()

        # Remove wake word if present
        if self.wake_word in command:
            command = command.replace(self.wake_word, "").strip()

        if not command:
            return Intent(
                command_type=CommandType.UNKNOWN,
                parameters={"raw_command": command},
                raw_input=raw_input,
                confidence=0.0,
            )

        try:
            # Add context from recent history if available
            context_message = self._build_context_message()
            full_message = (
                f"{context_message}\n\n{command}" if context_message else command
            )

            # Build tools for function calling
            tools = [genai.types.Tool(function_declarations=self.functions)]

            # Send message to Gemini using the new client API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_message,
                config=genai.types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    tools=tools,
                ),
            )

            # Check if the model used a function call
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        # Check for function call
                        if hasattr(part, "function_call") and part.function_call:
                            return self._convert_function_call_to_intent(
                                part.function_call, raw_input
                            )

                        # Check for text response (model asking for clarification)
                        elif hasattr(part, "text") and part.text:
                            # Model is asking for clarification
                            self._ask_for_clarification(part.text)
                            return Intent(
                                command_type=CommandType.UNKNOWN,
                                parameters={
                                    "raw_command": command,
                                    "clarification": part.text,
                                },
                                raw_input=raw_input,
                                confidence=0.3,
                            )

            # No function call or text, treat as unknown
            logger.warning(f"No function call or text in response for: {command}")
            return Intent(
                command_type=CommandType.UNKNOWN,
                parameters={"raw_command": command},
                raw_input=raw_input,
                confidence=0.5,
            )

        except Exception as e:
            # Check if this is a 503 error from Google Gemini API
            error_str = str(e)
            is_503_error = False

            # Check for 503 status code or UNAVAILABLE in the error message
            if "503" in error_str or "UNAVAILABLE" in error_str.upper():
                is_503_error = True

            if is_503_error:
                # Log as INFRA_FAILURE
                logger.error(
                    f"INFRA_FAILURE: Gemini API returned 503 (UNAVAILABLE) - {error_str}",
                    exc_info=True,
                )

                # Create GitHub issue synchronously
                try:
                    self._create_github_issue_for_infra_failure_sync(
                        e, f"Gemini API Error: {error_str}\nCommand: {command}"
                    )
                except Exception as issue_error:
                    logger.error(
                        f"Failed to create GitHub issue for 503 error: {issue_error}"
                    )
            else:
                logger.error(f"Error during LLM interpretation: {e}", exc_info=True)

            return Intent(
                command_type=CommandType.UNKNOWN,
                parameters={"raw_command": command, "error": str(e)},
                raw_input=raw_input,
                confidence=0.0,
            )

    def _convert_function_call_to_intent(self, function_call, raw_input: str) -> Intent:
        """Delegate to module-level helper in gemini_response_helpers."""
        return convert_function_call_to_intent(function_call, raw_input)

    def _ask_for_clarification(self, clarification_text: str) -> None:
        """
        Ask for clarification using the voice provider.

        Args:
            clarification_text: The clarification question from the LLM
        """
        if self.voice_provider:
            logger.info(f"Asking for clarification: {clarification_text}")
            self.voice_provider.speak(clarification_text)
        else:
            logger.warning(
                f"No voice provider available for clarification: {clarification_text}"
            )

    def is_exit_command(self, raw_input: str) -> bool:
        """
        Check if the input is an exit command.

        Args:
            raw_input: Raw text input

        Returns:
            True if it's an exit command
        """
        exit_keywords = ["fechar", "sair", "encerrar", "tchau"]
        command = raw_input.lower().strip()
        return any(keyword in command for keyword in exit_keywords)

    def is_cancel_command(self, raw_input: str) -> bool:
        """
        Check if the input is a cancel command.

        Args:
            raw_input: Raw text input

        Returns:
            True if it's a cancel command
        """
        cancel_keywords = ["cancelar", "parar", "stop"]
        command = raw_input.lower().strip()
        return any(keyword in command for keyword in cancel_keywords)

    def _build_context_message(self) -> str:
        """Delegate to module-level helper in gemini_response_helpers."""
        return build_context_message(self.history_provider)

    def generate_conversational_response(self, user_input: str) -> str:
        """
        Generate a conversational response for unknown commands or greetings.

        Args:
            user_input: User's input text

        Returns:
            Generated conversational response from the LLM
        """
        try:
            # Normalize input
            command = user_input.lower().strip()

            # Remove wake word if present
            if self.wake_word in command:
                command = command.replace(self.wake_word, "").strip()

            if not command:
                return "Olá! Como posso ajudar?"

            # Create a conversational prompt
            prompt = f"Responda de forma amigável e conversacional em português brasileiro: {command}"

            # Send to Gemini using the new client API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                ),
            )

            # Extract text response
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            return part.text.strip()

            return "Desculpe, não entendi. Pode repetir?"

        except Exception as e:
            logger.error(
                f"Error generating conversational response: {e}", exc_info=True
            )
            return "Desculpe, ocorreu um erro. Pode tentar novamente?"

# Nexus Compatibility
GeminiAdapter = LLMCommandAdapter
