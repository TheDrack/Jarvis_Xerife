# -*- coding: utf-8 -*-
"""Tests for Jarvis Engine"""

from unittest.mock import MagicMock, Mock, patch

import pytest


from app.core.config import settings
from app.core.engine import JarvisEngine


class TestJarvisEngine:
    """Test cases for JarvisEngine class"""

    @pytest.fixture
    def engine(self):
        """Create a JarvisEngine instance for testing"""
        with patch("pyttsx3.init"):
            return JarvisEngine()

    def test_engine_initialization(self, engine):
        """Test that engine initializes correctly"""
        assert engine is not None
        # The recognizer is now a MagicMock from conftest.py
        assert engine.recognizer is not None
        assert engine.is_running is False

    def test_speak(self):
        """Test speak method"""
        # Create a mock engine with say and runAndWait methods
        mock_engine = Mock()
        
        # Patch pyttsx3.init at the point where JarvisEngine imports and uses it
        with patch("app.core.engine.pyttsx3.init", return_value=mock_engine):
            # Create engine with the patched pyttsx3.init
            engine = JarvisEngine()
            
            # Call speak
            engine.speak("Olá")
            
            # Verify the calls
            mock_engine.say.assert_called_once_with("Olá")
            mock_engine.runAndWait.assert_called_once()

    @patch("speech_recognition.Microphone")
    @patch("pyttsx3.init")
    def test_listen_success(self, mock_tts_init, mock_microphone):
        """Test successful voice recognition"""
        engine = JarvisEngine()

        # Mock audio input - create an AudioSource-like object
        mock_source = MagicMock()
        mock_microphone.return_value.__enter__.return_value = mock_source

        # Mock recognition
        mock_audio = Mock()
        engine.recognizer.adjust_for_ambient_noise = Mock()
        engine.recognizer.listen = Mock(return_value=mock_audio)
        engine.recognizer.recognize_google = Mock(
            side_effect=[
                {"alternative": [{"transcript": "teste"}]},  # show_all=True
                "TESTE",  # Normal call
            ]
        )

        result = engine.listen()

        assert result == "teste"

    @patch("speech_recognition.Microphone")
    @patch("pyttsx3.init")
    def test_listen_no_speech(self, mock_tts_init, mock_microphone):
        """Test listen when no speech is detected"""
        engine = JarvisEngine()

        mock_source = MagicMock()
        mock_microphone.return_value.__enter__.return_value = mock_source

        mock_audio = Mock()
        engine.recognizer.adjust_for_ambient_noise = Mock()
        engine.recognizer.listen = Mock(return_value=mock_audio)
        engine.recognizer.recognize_google = Mock(return_value=[])  # Empty result

        result = engine.listen()

        assert result is None

    @patch("pyttsx3.init")
    def test_stop(self, mock_tts_init):
        """Test stop method"""
        engine = JarvisEngine()
        engine.is_running = True

        with pytest.raises(SystemExit):
            engine.stop()

        assert engine.is_running is False

    @patch("speech_recognition.Microphone")
    @patch("pyttsx3.init")
    def test_get_command_cancel(self, mock_tts_init, mock_microphone):
        """Test get_command with cancel keyword"""
        engine = JarvisEngine()

        mock_source = MagicMock()
        mock_microphone.return_value.__enter__.return_value = mock_source

        mock_audio = Mock()
        engine.recognizer.adjust_for_ambient_noise = Mock()
        engine.recognizer.listen = Mock(return_value=mock_audio)
        engine.recognizer.recognize_google = Mock(
            side_effect=[{"alternative": [{"transcript": "cancelar"}]}, "cancelar"]
        )

        # Mock speak to avoid actual TTS
        engine.speak = Mock()

        result = engine.get_command()

        assert result is None
        engine.speak.assert_called_with("Ação cancelada")


class TestJarvisEngineIntegration:
    """Integration tests for JarvisEngine"""

    @patch("pyttsx3.init")
    def test_engine_creates_successfully(self, mock_tts_init):
        """Test that engine can be created without errors"""
        mock_engine = Mock()
        mock_tts_init.return_value = mock_engine

        engine = JarvisEngine()

        assert engine is not None
        assert hasattr(engine, "speak")
        assert hasattr(engine, "listen")
        assert hasattr(engine, "stop")
