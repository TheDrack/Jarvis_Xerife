from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Tests for Configuration"""

from pathlib import Path

import pytest

from app.core.config import Settings, settings


class TestSettings(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test cases for Settings class"""

    def test_default_values(self):
        """Test that default values are set correctly"""
        test_settings = Settings()

        assert test_settings.app_name == "Jarvis Assistant"
        assert test_settings.version == "1.0.0"
        assert test_settings.language == "pt-BR"
        assert test_settings.wake_word == "xerife"

    def test_paths_creation(self):
        """Test that paths are created correctly"""
        test_settings = Settings()

        assert isinstance(test_settings.base_dir, Path)
        assert isinstance(test_settings.data_dir, Path)
        assert isinstance(test_settings.logs_dir, Path)

    def test_directories_exist(self):
        """Test that directories are created"""
        test_settings = Settings()

        # Directories should be created during initialization
        assert test_settings.data_dir.exists()
        assert test_settings.logs_dir.exists()

    def test_global_settings_instance(self):
        """Test that global settings instance exists"""
        assert settings is not None
        assert isinstance(settings, Settings)

    def test_pyautogui_settings(self):
        """Test PyAutoGUI related settings"""
        test_settings = Settings()

        assert test_settings.pyautogui_pause == 0.4
        assert test_settings.search_timeout == 7.5

    def test_audio_settings(self):
        """Test audio related settings"""
        test_settings = Settings()

        assert test_settings.ambient_noise_adjustment is True
        assert test_settings.recognition_timeout is None
