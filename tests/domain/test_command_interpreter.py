# -*- coding: utf-8 -*-
"""Tests for Domain layer - Command Interpreter"""

import pytest

from app.domain.models import CommandType
from app.domain.services import CommandInterpreter


class TestCommandInterpreter:
    """Test cases for CommandInterpreter - pure business logic"""

    @pytest.fixture
    def interpreter(self):
        """Create a CommandInterpreter instance"""
        return CommandInterpreter(wake_word="xerife")

    def test_interpret_type_command(self, interpreter):
        """Test interpretation of type command"""
        intent = interpreter.interpret("escreva hello world")

        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters["text"] == "hello world"
        assert intent.confidence == 1.0

    def test_interpret_press_key_command(self, interpreter):
        """Test interpretation of press key command"""
        intent = interpreter.interpret("aperte enter")

        assert intent.command_type == CommandType.PRESS_KEY
        assert intent.parameters["key"] == "enter"

    def test_interpret_open_browser_command(self, interpreter):
        """Test interpretation of open browser command"""
        intent = interpreter.interpret("internet")

        assert intent.command_type == CommandType.OPEN_BROWSER
        assert intent.parameters == {}

    def test_interpret_open_url_command(self, interpreter):
        """Test interpretation of open URL command"""
        intent = interpreter.interpret("site google.com")

        assert intent.command_type == CommandType.OPEN_URL
        assert intent.parameters["url"] == "https://google.com"

    def test_interpret_url_with_https(self, interpreter):
        """Test that URLs with https are not modified"""
        intent = interpreter.interpret("site https://example.com")

        assert intent.parameters["url"] == "https://example.com"

    def test_interpret_search_command(self, interpreter):
        """Test interpretation of search command"""
        intent = interpreter.interpret("clicar em botão")

        assert intent.command_type == CommandType.SEARCH_ON_PAGE
        assert intent.parameters["search_text"] == "botão"

    def test_interpret_unknown_command(self, interpreter):
        """Test interpretation of unknown command"""
        intent = interpreter.interpret("comando inexistente")

        assert intent.command_type == CommandType.UNKNOWN
        assert "raw_command" in intent.parameters
        assert intent.confidence == 0.5

    def test_remove_wake_word(self, interpreter):
        """Test that wake word is removed from command"""
        intent = interpreter.interpret("xerife escreva teste")

        assert intent.command_type == CommandType.TYPE_TEXT
        assert intent.parameters["text"] == "teste"
        assert "xerife" not in intent.parameters["text"]

    def test_is_exit_command(self, interpreter):
        """Test exit command detection"""
        assert interpreter.is_exit_command("fechar") is True
        assert interpreter.is_exit_command("sair") is True
        assert interpreter.is_exit_command("encerrar") is True
        assert interpreter.is_exit_command("tchau") is True
        assert interpreter.is_exit_command("escreva algo") is False

    def test_is_cancel_command(self, interpreter):
        """Test cancel command detection"""
        assert interpreter.is_cancel_command("cancelar") is True
        assert interpreter.is_cancel_command("parar") is True
        assert interpreter.is_cancel_command("stop") is True
        assert interpreter.is_cancel_command("escreva algo") is False

    def test_case_insensitive(self, interpreter):
        """Test that interpretation is case insensitive"""
        intent1 = interpreter.interpret("ESCREVA TESTE")
        intent2 = interpreter.interpret("escreva teste")

        assert intent1.command_type == intent2.command_type
        assert intent1.parameters == intent2.parameters

    def test_interpret_report_issue_command(self, interpreter):
        """Test interpretation of report issue command"""
        intent = interpreter.interpret("reporte que o botão X está quebrado")

        assert intent.command_type == CommandType.REPORT_ISSUE
        assert intent.parameters["issue_description"] == "que o botão X está quebrado"
        # Verify original casing is preserved
        assert "X" in intent.parameters["issue_description"]
        assert "context" in intent.parameters

    def test_interpret_issue_command(self, interpreter):
        """Test interpretation of issue command"""
        intent = interpreter.interpret("issue sobre a lentidão no Groq")

        assert intent.command_type == CommandType.REPORT_ISSUE
        assert intent.parameters["issue_description"] == "sobre a lentidão no Groq"
