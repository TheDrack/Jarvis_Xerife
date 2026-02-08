# -*- coding: utf-8 -*-
"""Gemini LLM Adapter - Google Generative AI integration for command interpretation

Note: This adapter uses google.generativeai library (version 0.3.0+).
The library internally uses the Google AI Generative Language API.
Default model is 'gemini-1.5-flash' for stability and wide availability.
"""

import asyncio
import logging
import os
from typing import Optional

import google.generativeai as genai

from app.application.ports import VoiceProvider
from app.domain.models import CommandType, Intent
from app.domain.services.agent_service import AgentService

logger = logging.getLogger(__name__)


class LLMCommandAdapter:
    """
    Adapter that uses Google Gemini API to interpret commands using Function Calling.
    Converts AI responses into Intent objects that IntentProcessor understands.
    Uses AsyncIO to avoid blocking the voice loop.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-flash",
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
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY or GEMINI_API_KEY must be provided or set in environment variables"
            )

        # Configure Gemini with REST transport to avoid gRPC issues
        genai.configure(api_key=self.api_key, transport='rest')

        # Get function declarations from AgentService
        self.functions = AgentService.get_function_declarations()
        self.system_instruction = AgentService.get_system_instruction()

        # Initialize the model with function calling
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            tools=[{"function_declarations": self.functions}],
            system_instruction=self.system_instruction,
        )

        # Start a chat session
        self.chat = self.model.start_chat(enable_automatic_function_calling=False)

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
            full_message = f"{context_message}\n\n{command}" if context_message else command

            # Send message to Gemini in a separate thread to avoid blocking
            response = await asyncio.to_thread(
                self.chat.send_message, full_message
            )

            # Check if the model used a function call
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]

                # Check for function call
                if hasattr(part, "function_call") and part.function_call:
                    function_call = part.function_call
                    return self._convert_function_call_to_intent(
                        function_call, raw_input
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
            logger.error(f"Error during LLM interpretation: {e}")
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
            full_message = f"{context_message}\n\n{command}" if context_message else command

            # Send message to Gemini
            response = self.chat.send_message(full_message)

            # Check if the model used a function call
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]

                # Check for function call
                if hasattr(part, "function_call") and part.function_call:
                    function_call = part.function_call
                    return self._convert_function_call_to_intent(
                        function_call, raw_input
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
            logger.error(f"Error during LLM interpretation: {e}")
            return Intent(
                command_type=CommandType.UNKNOWN,
                parameters={"raw_command": command, "error": str(e)},
                raw_input=raw_input,
                confidence=0.0,
            )

    def _convert_function_call_to_intent(
        self, function_call, raw_input: str
    ) -> Intent:
        """
        Convert a Gemini function call to an Intent object.

        Args:
            function_call: The function call from Gemini response
            raw_input: Original user input

        Returns:
            Intent object
        """
        function_name = function_call.name
        function_args = dict(function_call.args) if function_call.args else {}

        # Map function name to command type
        command_type = AgentService.map_function_to_command_type(function_name)

        # Build parameters
        parameters = self._build_parameters(command_type, function_args)

        logger.info(
            f"LLM function call: {function_name} with args: {function_args} -> {command_type}"
        )

        return Intent(
            command_type=command_type,
            parameters=parameters,
            raw_input=raw_input,
            confidence=0.9,  # High confidence when LLM provides a function call
        )

    def _build_parameters(self, command_type: CommandType, function_args: dict) -> dict:
        """
        Build parameters dictionary based on command type and function arguments.

        Args:
            command_type: Type of command
            function_args: Arguments from function call

        Returns:
            Dictionary of parameters
        """
        if command_type == CommandType.TYPE_TEXT:
            return {"text": function_args.get("text", "")}

        elif command_type == CommandType.PRESS_KEY:
            return {"key": function_args.get("key", "")}

        elif command_type == CommandType.OPEN_BROWSER:
            return {}

        elif command_type == CommandType.OPEN_URL:
            url = function_args.get("url", "")
            # Add https:// if not present
            if url and not url.startswith("http"):
                url = f"https://{url}"
            return {"url": url}

        elif command_type == CommandType.SEARCH_ON_PAGE:
            return {"search_text": function_args.get("search_text", "")}

        return function_args

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
        """
        Build context message from the last 3 commands in history.

        Returns:
            Formatted context string or empty string if no history
        """
        if not self.history_provider:
            return ""

        try:
            # Get last 3 commands from history
            recent_history = self.history_provider.get_recent_history(limit=3)
            if not recent_history:
                return ""

            # Build context message
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
            
            # Send to Gemini
            response = self.chat.send_message(prompt)
            
            # Extract text response
            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]
                if hasattr(part, "text") and part.text:
                    return part.text.strip()
            
            return "Desculpe, não entendi. Pode repetir?"
            
        except Exception as e:
            logger.error(f"Error generating conversational response: {e}")
            return "Desculpe, ocorreu um erro. Pode tentar novamente?"
