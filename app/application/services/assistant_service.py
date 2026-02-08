# -*- coding: utf-8 -*-
"""Assistant Service - Main use case orchestrator"""

import logging
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from app.application.ports import ActionProvider, HistoryProvider, VoiceProvider, WebProvider
from app.application.services.dependency_manager import DependencyManager
from app.domain.models import CommandType, Intent, Response
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
        history_provider: Optional[HistoryProvider] = None,
        dependency_manager: Optional[DependencyManager] = None,
        wake_word: str = "xerife",
        gemini_adapter: Optional[Any] = None,
        device_service: Optional[Any] = None,
    ):
        """
        Initialize the assistant service with injected dependencies

        Args:
            voice_provider: Voice input/output adapter
            action_provider: System automation adapter
            web_provider: Web navigation adapter
            command_interpreter: Domain service for command interpretation
            intent_processor: Domain service for intent processing
            history_provider: Optional history persistence adapter
            dependency_manager: Optional dependency manager for on-demand package installation
            wake_word: Wake word for activation
            gemini_adapter: Optional Gemini adapter for conversational AI
            device_service: Optional device service for distributed orchestration
        """
        self.voice = voice_provider
        self.action = action_provider
        self.web = web_provider
        self.interpreter = command_interpreter
        self.processor = intent_processor
        self.history = history_provider
        self.dependency_manager = dependency_manager or DependencyManager()
        self.wake_word = wake_word
        self.gemini_adapter = gemini_adapter
        self.device_service = device_service
        self.is_running = False
        # Command history tracking (max 100 commands)
        self._command_history: Deque[Dict[str, Any]] = deque(maxlen=100)
        
        # Log error if assistant is started without AI adapter
        if self.gemini_adapter is None:
            logger.error("ERRO: Assistente iniciado sem adaptador de IA")

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

        # Handle unknown commands with conversational AI if available
        if intent.command_type == CommandType.UNKNOWN:
            # Debug prints for fallback logic
            print(f"DEBUG: Gemini Adapter status: {self.gemini_adapter is not None}")
            print(f"DEBUG: Intent command type: {intent.command_type}")
            
            # Check if interpreter has conversational capability (LLMCommandAdapter)
            if hasattr(self.interpreter, 'generate_conversational_response'):
                logger.info("Unknown command detected, using conversational AI")
                try:
                    conversational_response = self.interpreter.generate_conversational_response(user_input)
                    response = Response(
                        success=True,
                        message=conversational_response,
                        data={
                            "command_type": CommandType.CHAT.value,
                            "parameters": {"user_input": user_input},
                        }
                    )
                    self._add_to_history(user_input, response)
                    return response
                except Exception as e:
                    logger.error(f"Error generating conversational response: {e}")
                    # Fall through to validation error
            
            # Fallback to validation error if no conversational AI or error occurred
            return self._handle_validation_error(user_input, intent)

        # Validate the intent
        validation = self.processor.validate_intent(intent)
        if not validation.success:
            logger.warning(f"Invalid intent: {validation.message}")
            return self._handle_validation_error(user_input, intent, validation)

        # Create command
        command = self.processor.create_command(intent)

        # Execute the command with device routing if applicable
        response = self._execute_command(command.intent.command_type, command.intent.parameters)
        # Add command metadata to response for history tracking
        if response.data is None:
            response.data = {}
        response.data["command_type"] = command.intent.command_type.value
        response.data["parameters"] = command.intent.parameters
        self._add_to_history(user_input, response)
        return response

    def _handle_validation_error(
        self, user_input: str, intent: Intent, validation: Optional[Response] = None
    ) -> Response:
        """
        Handle validation errors by adding metadata and recording to history

        Args:
            user_input: Original user input
            intent: The intent that failed validation
            validation: Optional validation response from processor

        Returns:
            Response object with validation error
        """
        if validation is None:
            validation = self.processor.validate_intent(intent)
        
        # Add command metadata for failed validations
        if validation.data is None:
            validation.data = {}
        validation.data["command_type"] = intent.command_type.value
        validation.data["parameters"] = intent.parameters
        self._add_to_history(user_input, validation)
        return validation

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
            # Speak the response message if it's a chat/conversation
            if response.success and response.data and response.data.get("command_type") == CommandType.CHAT.value:
                self.voice.speak(response.message)
            elif not response.success and response.error == "UNKNOWN_COMMAND":
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
        Execute a command based on its type with device routing support

        Args:
            command_type: Type of command to execute
            params: Command parameters

        Returns:
            Response object with execution result
        """
        try:
            # Check if command requires a specific device capability
            required_capability = self._get_required_capability(command_type, params)
            
            # If a capability is required and device_service is available, route to device
            if required_capability and self.device_service:
                target_device = self.device_service.find_device_by_capability(required_capability)
                if target_device:
                    logger.info(f"Routing command to device: {target_device['name']} (ID: {target_device['id']})")
                    # Add target_device_id to response for distributed execution
                    return Response(
                        success=True,
                        message=f"Command routed to device: {target_device['name']}",
                        data={
                            "target_device_id": target_device["id"],
                            "target_device_name": target_device["name"],
                            "required_capability": required_capability,
                            "requires_device_execution": True,
                        }
                    )
                else:
                    logger.warning(f"No online device found with capability: {required_capability}")
                    return Response(
                        success=False,
                        message=f"No device available with capability: {required_capability}",
                        error="NO_DEVICE_AVAILABLE",
                    )
            
            # Standard capability check for local execution
            if required_capability:
                logger.info(f"Command requires capability: {required_capability}")
                if not self.dependency_manager.ensure_capability(required_capability):
                    return Response(
                        success=False,
                        message=f"Failed to ensure required capability: {required_capability}",
                        error="MISSING_DEPENDENCY",
                    )

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

            elif command_type == CommandType.CHAT:
                # Chat responses are already handled in process_command
                # This case should not normally be reached, but return success
                message = params.get("response", "")
                return Response(success=True, message=message)

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

    def get_command_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent command history

        Args:
            limit: Maximum number of commands to return (default: 5)

        Returns:
            List of command history items
        """
        history_list = list(self._command_history)
        # Return most recent first
        return history_list[-limit:][::-1] if history_list else []

    def _add_to_history(self, command: str, response: Response) -> None:
        """
        Add a command to history

        Args:
            command: The command that was executed
            response: The response from execution
        """
        history_item = {
            "command": command,
            "timestamp": datetime.now().astimezone().isoformat(),
            "success": response.success,
            "message": response.message,
        }
        self._command_history.append(history_item)
        logger.debug(f"Added to history: {command}")

        # Save to persistent storage if history provider is available
        if self.history:
            # Extract command type from response data if available
            command_type = "unknown"
            parameters = {}
            if hasattr(response, 'data') and response.data:
                command_type = response.data.get("command_type", "unknown")
                parameters = response.data.get("parameters", {})

            self.history.save_interaction(
                user_input=command,
                command_type=command_type,
                parameters=parameters,
                success=response.success,
                response_text=response.message,
            )

    def _get_required_capability(self, command_type: CommandType, params: dict) -> Optional[str]:
        """
        Determine if a command requires a specific capability/library

        Args:
            command_type: Type of command to execute
            params: Command parameters

        Returns:
            Name of required capability, or None if no special capability is needed

        Note:
            This is currently a placeholder that returns None for all commands.
            In the future, this can be extended to check params for things like:
            - "analyze data" -> "pandas"
            - "web automation" -> "playwright"
            - "image processing" -> "opencv"
            
            The infrastructure is in place to automatically install dependencies
            when needed once specific command types require them.
        """
        # This can be extended based on command parameters or types
        # For now, we return None for standard commands
        return None
