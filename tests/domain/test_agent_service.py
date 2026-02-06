# -*- coding: utf-8 -*-
"""Tests for Domain layer - Agent Service"""

from app.domain.models import CommandType
from app.domain.services import AgentService


class TestAgentService:
    """Test cases for AgentService - LLM function calling configuration"""

    def test_get_function_declarations(self):
        """Test that function declarations are properly defined"""
        functions = AgentService.get_function_declarations()

        assert isinstance(functions, list)
        assert len(functions) == 5  # type_text, press_key, open_browser, open_url, search_on_page

        # Check that all expected functions are present
        function_names = [f["name"] for f in functions]
        assert "type_text" in function_names
        assert "press_key" in function_names
        assert "open_browser" in function_names
        assert "open_url" in function_names
        assert "search_on_page" in function_names

    def test_type_text_function_declaration(self):
        """Test type_text function declaration structure"""
        functions = AgentService.get_function_declarations()
        type_text_func = next(f for f in functions if f["name"] == "type_text")

        assert "description" in type_text_func
        assert "parameters" in type_text_func
        assert type_text_func["parameters"]["type"] == "object"
        assert "text" in type_text_func["parameters"]["properties"]
        assert "text" in type_text_func["parameters"]["required"]

    def test_press_key_function_declaration(self):
        """Test press_key function declaration structure"""
        functions = AgentService.get_function_declarations()
        press_key_func = next(f for f in functions if f["name"] == "press_key")

        assert "description" in press_key_func
        assert "parameters" in press_key_func
        assert "key" in press_key_func["parameters"]["properties"]
        assert "key" in press_key_func["parameters"]["required"]

    def test_open_browser_function_declaration(self):
        """Test open_browser function declaration structure"""
        functions = AgentService.get_function_declarations()
        open_browser_func = next(f for f in functions if f["name"] == "open_browser")

        assert "description" in open_browser_func
        assert "parameters" in open_browser_func
        # open_browser should have no required parameters
        assert not open_browser_func["parameters"].get("required")

    def test_open_url_function_declaration(self):
        """Test open_url function declaration structure"""
        functions = AgentService.get_function_declarations()
        open_url_func = next(f for f in functions if f["name"] == "open_url")

        assert "description" in open_url_func
        assert "parameters" in open_url_func
        assert "url" in open_url_func["parameters"]["properties"]
        assert "url" in open_url_func["parameters"]["required"]

    def test_search_on_page_function_declaration(self):
        """Test search_on_page function declaration structure"""
        functions = AgentService.get_function_declarations()
        search_func = next(f for f in functions if f["name"] == "search_on_page")

        assert "description" in search_func
        assert "parameters" in search_func
        assert "search_text" in search_func["parameters"]["properties"]
        assert "search_text" in search_func["parameters"]["required"]

    def test_map_function_to_command_type(self):
        """Test mapping function names to command types"""
        assert AgentService.map_function_to_command_type("type_text") == CommandType.TYPE_TEXT
        assert AgentService.map_function_to_command_type("press_key") == CommandType.PRESS_KEY
        assert AgentService.map_function_to_command_type("open_browser") == CommandType.OPEN_BROWSER
        assert AgentService.map_function_to_command_type("open_url") == CommandType.OPEN_URL
        assert AgentService.map_function_to_command_type("search_on_page") == CommandType.SEARCH_ON_PAGE

    def test_map_unknown_function(self):
        """Test mapping unknown function name returns UNKNOWN"""
        assert AgentService.map_function_to_command_type("unknown_function") == CommandType.UNKNOWN

    def test_get_system_instruction(self):
        """Test that system instruction is properly defined"""
        instruction = AgentService.get_system_instruction()

        assert isinstance(instruction, str)
        assert len(instruction) > 0
        # Check that it mentions Xerife
        assert "Xerife" in instruction or "xerife" in instruction
        # Check that it mentions productivity/automation
        assert "produtividade" in instruction.lower() or "automação" in instruction.lower()
        # Check that it mentions being concise
        assert "conciso" in instruction.lower() or "eficiente" in instruction.lower()

    def test_system_instruction_has_examples(self):
        """Test that system instruction includes examples"""
        instruction = AgentService.get_system_instruction()

        # Should have examples of commands
        assert "type_text" in instruction or "escreva" in instruction.lower()
        assert "press_key" in instruction or "aperte" in instruction.lower()

    def test_function_descriptions_in_portuguese(self):
        """Test that function descriptions are in Portuguese"""
        functions = AgentService.get_function_declarations()

        portuguese_found = False
        for func in functions:
            description = func["description"]
            # Check for Portuguese words
            if any(
                word in description.lower()
                for word in ["digita", "texto", "teclado", "pressiona", "tecla", "abre", "navegador"]
            ):
                portuguese_found = True
                break

        assert portuguese_found, "No Portuguese keywords found in any function descriptions"
