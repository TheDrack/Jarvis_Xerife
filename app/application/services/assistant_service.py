# -*- coding: utf-8 -*-
"""Assistant Service - Main use case orchestrator"""

import logging

from app.application.ports import ActionProvider, VoiceProvider, WebProvider
from app.domain.models import CommandType, Response
from app.domain.services import CommandInterpreter, IntentProcessor

logger = logging.getLogger(__name__)


class AssistantService:
    """
    Main application service that orchestrates the assistant's behavior.
    Uses dependency injection for all external dependencies (ports).
    """

    def __init__(
        self,
        voice_provider: VoiceProvider,
        action_provider: ActionProvider,
        web_provider: WebProvider,
        command_interpreter: CommandInterpreter,
        intent_processor: IntentProcessor,
        wake_word: str = "xerife",
    ):
        """
        Initialize the assistant service with injected dependencies

        Args:
            voice_provider: Voice input/output adapter
            action_provider: System automation adapter
            web_provider: Web navigation adapter
            command_interpreter: Domain service for command interpretation
            intent_processor: Domain service for intent processing
            wake_word: Wake word for activation
        """
        self.voice = voice_provider
        self.action = action_provider
        self.web = web_provider
        self.interpreter = command_interpreter
        self.processor = intent_processor
        self.wake_word = wake_word
        self.is_running = False

    def start(self) -> None:
        """Start the assistant and listen for commands"""
        self.is_running = True
        self.voice.speak(f"Não tema, {self.wake_word} chegou")
        logger.info("Assistant started")

        while self.is_running:
            try:
                # Listen for voice input
                user_input = self.voice.listen()

                if not user_input:
                    continue

                # Check for wake word or special commands
                if self.wake_word in user_input.lower():
                    self._handle_wake_word(user_input)
                elif self.interpreter.is_exit_command(user_input):
                    self._handle_exit()
                    break

            except KeyboardInterrupt:
                self._handle_exit()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                continue

    def process_command(self, user_input: str) -> Response:
        """
        Process a single command

        Args:
            user_input: Raw user input

        Returns:
            Response object with execution result
        """
        # Interpret the command
        intent = self.interpreter.interpret(user_input)
        logger.info(f"Interpreted intent: {intent.command_type} with params: {intent.parameters}")

        # Validate the intent
        validation = self.processor.validate_intent(intent)
        if not validation.success:
            logger.warning(f"Invalid intent: {validation.message}")
            return validation

        # Create command
        command = self.processor.create_command(intent)

        # Execute the command
        return self._execute_command(command.intent.command_type, command.intent.parameters)

    def _handle_wake_word(self, user_input: str) -> None:
        """
        Handle input containing the wake word

        Args:
            user_input: Raw user input with wake word
        """
        # Remove wake word and process
        command_text = user_input.lower().replace(f"{self.wake_word} ", "").strip()

        self.voice.speak("Olá")

        if command_text:
            # Process the command immediately
            response = self.process_command(command_text)
            if not response.success and response.error == "UNKNOWN_COMMAND":
                logger.warning(f"Unknown command: {command_text}")
        else:
            # Ask for a new command
            self.voice.speak("Diga um comando")
            new_input = self.voice.listen()
            if new_input:
                self.process_command(new_input)

    def _handle_exit(self) -> None:
        """Handle exit command"""
        self.is_running = False
        self.voice.speak("Fechando assistente, até a próxima...")
        logger.info("Assistant stopped")

    def _execute_command(self, command_type: CommandType, params: dict) -> Response:
        """
        Execute a command based on its type

        Args:
            command_type: Type of command to execute
            params: Command parameters

        Returns:
            Response object with execution result
        """
        try:
            if command_type == CommandType.TYPE_TEXT:
                text = params.get("text", "")
                self.action.type_text(text)
                return Response(success=True, message=f"Typed: {text}")

            elif command_type == CommandType.PRESS_KEY:
                key = params.get("key", "")
                self.action.press_key(key)
                return Response(success=True, message=f"Pressed: {key}")

            elif command_type == CommandType.OPEN_BROWSER:
                self.action.hotkey("ctrl", "shift", "c")
                return Response(success=True, message="Opened browser")

            elif command_type == CommandType.OPEN_URL:
                url = params.get("url", "")
                self.web.open_url(url)
                return Response(success=True, message=f"Opened: {url}")

            elif command_type == CommandType.SEARCH_ON_PAGE:
                search_text = params.get("search_text", "")
                self.web.search_on_page(search_text)
                return Response(success=True, message=f"Searched: {search_text}")

            else:
                return Response(
                    success=False,
                    message=f"Unsupported command type: {command_type}",
                    error="UNSUPPORTED_COMMAND",
                )

        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return Response(success=False, message=str(e), error="EXECUTION_ERROR")

    def stop(self) -> None:
        """Stop the assistant"""
        self.is_running = False
        logger.info("Assistant stop requested")
