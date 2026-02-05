# -*- coding: utf-8 -*-
"""Edge adapters - Local hardware and UI dependencies"""
from .automation_adapter import AutomationAdapter
from .keyboard_adapter import KeyboardAdapter
from .tts_adapter import TTSAdapter
from .voice_adapter import VoiceAdapter
from .web_adapter import WebAdapter

__all__ = [
    "VoiceAdapter",
    "TTSAdapter",
    "AutomationAdapter",
    "KeyboardAdapter",
    "WebAdapter",
]
