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
sys.modules["pyperclip"] = MagicMock()

# Mock Google Generative AI for testing without API key
sys.modules["google"] = MagicMock()
sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
sys.modules["google.ai"] = MagicMock()
sys.modules["google.ai.generativelanguage"] = MagicMock()

# Legacy modules removed from the current codebase.
# Keep the old fixtures loadable so that tests importing the conftest
# do not fail at collection time. They fall back to a controlled mock when
# the legacy implementation is not present.
sys.modules.setdefault("app.core.engine", MagicMock())
sys.modules.setdefault("app.actions.system_commands", MagicMock())


@pytest.fixture(autouse=True)
def _restore_default_event_loop():
    """Garante um event loop padrão utilizável para testes síncronos.

    ``asyncio_mode = auto`` faz o pytest-asyncio encerrar o loop após cada
    teste assíncrono, deixando a policy sem loop na thread principal. Testes
    síncronos que usam ``asyncio.get_event_loop()`` então quebram com
    ``RuntimeError: There is no current event loop`` — dependendo apenas da
    ordem de execução (o mesmo teste passa isolado e falha na suíte completa).

    Recriamos um loop padrão no teardown quando a policy ficou sem loop aberto.
    """
    yield

    import asyncio

    policy = asyncio.get_event_loop_policy()
    try:
        loop = policy.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("event loop closed")
    except Exception:
        try:
            policy.set_event_loop(policy.new_event_loop())
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _ambiente_sem_chaves_de_api(monkeypatch):
    """Os testes não podem depender de chaves reais do ambiente.

    No CI, os secrets (GROQ_API_KEY, GEMINI_API_KEY...) são injetados no passo de
    testes. Sem esta limpeza, testes que assumem "sem chave" passam localmente e
    falham no CI. Aqui cada teste começa sem chaves, como numa máquina limpa.
    """
    for var in (
        "GROQ_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY",
        "MISTRAL_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def anyio_backend():
    """Configure the backend for anyio tests"""
    return 'asyncio'


@pytest.fixture
def mock_engine():
    """Mock JarvisEngine for testing"""
    from unittest.mock import Mock, patch

    with patch("pyttsx3.init"):
        try:
            from app.core.engine import JarvisEngine
        except Exception:
            JarvisEngine = MagicMock

        engine = JarvisEngine()
        engine.speak = Mock()
        engine.listen = Mock(return_value="test command")
        return engine


@pytest.fixture
def mock_system_commands():
    """Mock SystemCommands for testing"""
    from unittest.mock import Mock

    try:
        from app.actions.system_commands import SystemCommands
    except Exception:
        SystemCommands = MagicMock

    sys_cmd = SystemCommands()
    sys_cmd.type_text = Mock()
    sys_cmd.press_key = Mock()
    sys_cmd.hotkey = Mock()
    return sys_cmd
