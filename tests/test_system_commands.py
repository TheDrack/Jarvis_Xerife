# -*- coding: utf-8 -*-
"""Tests for System Commands"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.actions.system_commands import (
    SystemCommands,
    WebNavigator,
    CommandProcessor
)


class TestSystemCommands:
    """Test cases for SystemCommands class"""
    
    @pytest.fixture
    def system_commands(self):
        """Create a SystemCommands instance for testing"""
        return SystemCommands()
    
    def test_initialization(self, system_commands):
        """Test that SystemCommands initializes correctly"""
        assert system_commands is not None
        assert system_commands.keyboard is not None
    
    @patch('app.actions.system_commands.Controller')
    def test_type_text(self, mock_controller):
        """Test type_text method"""
        mock_kb = Mock()
        mock_controller.return_value = mock_kb
        
        sys_cmd = SystemCommands()
        sys_cmd.type_text("Hello")
        
        mock_kb.type.assert_called_once_with("Hello")
    
    @patch('pyautogui.press')
    def test_press_key(self, mock_press, system_commands):
        """Test press_key method"""
        system_commands.press_key('enter')
        mock_press.assert_called_once_with('enter')
    
    @patch('pyautogui.hotkey')
    def test_hotkey(self, mock_hotkey, system_commands):
        """Test hotkey method"""
        system_commands.hotkey('ctrl', 'c')
        mock_hotkey.assert_called_once_with('ctrl', 'c')
    
    @patch('pyautogui.click')
    def test_click(self, mock_click, system_commands):
        """Test click method"""
        system_commands.click(100, 200)
        mock_click.assert_called_once_with(100, 200, button='left', clicks=1)


class TestWebNavigator:
    """Test cases for WebNavigator class"""
    
    @pytest.fixture
    def web_navigator(self):
        """Create a WebNavigator instance for testing"""
        mock_sys_cmd = Mock()
        return WebNavigator(mock_sys_cmd)
    
    @patch('webbrowser.open')
    def test_open_url(self, mock_open, web_navigator):
        """Test open_url method"""
        web_navigator.open_url("https://example.com")
        mock_open.assert_called_once_with("https://example.com")
    
    def test_search_on_page(self, web_navigator):
        """Test search_on_page method"""
        web_navigator.search_on_page("test")
        
        web_navigator.sys_cmd.hotkey.assert_called_once_with('ctrl', 'f')
        web_navigator.sys_cmd.type_text.assert_called_once_with("test")


class TestCommandProcessor:
    """Test cases for CommandProcessor class"""
    
    @pytest.fixture
    def command_processor(self):
        """Create a CommandProcessor instance for testing"""
        mock_sys_cmd = Mock()
        mock_web_nav = Mock()
        return CommandProcessor(mock_sys_cmd, mock_web_nav)
    
    def test_initialization(self, command_processor):
        """Test that CommandProcessor initializes correctly"""
        assert command_processor is not None
        assert command_processor.commands_map is not None
        assert len(command_processor.commands_map) > 0
    
    def test_handle_type_command(self, command_processor):
        """Test processing type command"""
        command_processor.process("escreva olá")
        command_processor.sys_cmd.type_text.assert_called()
    
    def test_handle_press_command(self, command_processor):
        """Test processing press command"""
        command_processor.process("aperte enter")
        command_processor.sys_cmd.press_key.assert_called()
    
    def test_unknown_command(self, command_processor, capsys):
        """Test processing unknown command"""
        command_processor.process("comando desconhecido")
        captured = capsys.readouterr()
        assert "Unknown command" in captured.out
