# -*- coding: utf-8 -*-
"""Pytest configuration and fixtures"""

import sys
from unittest.mock import MagicMock

import pytest

# Mock hardware-related modules for testing without hardware/display
# This must happen before any imports of modules that depend on these
sys.modules["pyautogui"] = MagicMock()
sys.modules["pynput"] = MagicMock()
sys.modules["pynput.keyboard"] = MagicMock()
sys.modules["speech_recognition"] = MagicMock()
sys.modules["pyttsx3"] = MagicMock()


@pytest.fixture
def mock_engine():
    """Mock JarvisEngine for testing"""
    from unittest.mock import Mock, patch

    with patch("pyttsx3.init"):
        from app.core.engine import JarvisEngine

        engine = JarvisEngine()
        engine.speak = Mock()
        engine.listen = Mock(return_value="test command")
        return engine


@pytest.fixture
def mock_system_commands():
    """Mock SystemCommands for testing"""
    from unittest.mock import Mock

    from app.actions.system_commands import SystemCommands

    sys_cmd = SystemCommands()
    sys_cmd.type_text = Mock()
    sys_cmd.press_key = Mock()
    sys_cmd.hotkey = Mock()
    return sys_cmd
