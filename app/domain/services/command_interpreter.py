# -*- coding: utf-8 -*-
"""Command Interpreter - Pure business logic for interpreting user commands"""

from app.domain.models import CommandType, Intent


class CommandInterpreter:
    """
    Interprets raw text commands into structured Intents.
    Pure Python, no dependencies on hardware or frameworks.
    """

    def __init__(self, wake_word: str = "xerife"):
        """
        Initialize the command interpreter

        Args:
            wake_word: The wake word to filter out from commands
        """
        self.wake_word = wake_word
        self._command_patterns = {
            "escreva": CommandType.TYPE_TEXT,
            "digite": CommandType.TYPE_TEXT,
            "aperte": CommandType.PRESS_KEY,
            "pressione": CommandType.PRESS_KEY,
            "internet": CommandType.OPEN_BROWSER,
            "navegador": CommandType.OPEN_BROWSER,
            "site": CommandType.OPEN_URL,
            "abrir": CommandType.OPEN_URL,
            "clicar em": CommandType.SEARCH_ON_PAGE,
            "procurar": CommandType.SEARCH_ON_PAGE,
        }

    def interpret(self, raw_input: str) -> Intent:
        """
        Interpret a raw text command into a structured Intent

        Args:
            raw_input: Raw text from voice or text input

        Returns:
            Intent object with command type and parameters
        """
        # Normalize input
        command = raw_input.lower().strip()

        # Remove wake word if present (handle both with and without space)
        if self.wake_word in command:
            command = command.replace(self.wake_word, "").strip()

        # Parse command
        for pattern, command_type in self._command_patterns.items():
            if pattern in command:
                # Extract parameter by removing the pattern
                param = command.replace(f"{pattern} ", "").strip()

                # Build parameters based on command type
                parameters = self._build_parameters(command_type, param, command)

                return Intent(
                    command_type=command_type,
                    parameters=parameters,
                    raw_input=raw_input,
                    confidence=1.0,
                )

        # Unknown command
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": command},
            raw_input=raw_input,
            confidence=0.5,
        )

    def _build_parameters(self, command_type: CommandType, param: str, full_command: str) -> dict:
        """
        Build parameters dictionary based on command type

        Args:
            command_type: Type of command
            param: Extracted parameter from command
            full_command: Full command string

        Returns:
            Dictionary of parameters
        """
        if command_type == CommandType.TYPE_TEXT:
            return {"text": param}

        elif command_type == CommandType.PRESS_KEY:
            return {"key": param}

        elif command_type == CommandType.OPEN_BROWSER:
            return {}

        elif command_type == CommandType.OPEN_URL:
            # Add https:// if not present
            url = param
            if url and not url.startswith("http"):
                url = f"https://{url}"
            return {"url": url}

        elif command_type == CommandType.SEARCH_ON_PAGE:
            return {"search_text": param}

        return {"param": param}

    def is_exit_command(self, raw_input: str) -> bool:
        """
        Check if the input is an exit command

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
        Check if the input is a cancel command

        Args:
            raw_input: Raw text input

        Returns:
            True if it's a cancel command
        """
        cancel_keywords = ["cancelar", "parar", "stop"]
        command = raw_input.lower().strip()
        return any(keyword in command for keyword in cancel_keywords)
