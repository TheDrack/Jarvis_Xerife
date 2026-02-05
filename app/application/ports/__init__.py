# -*- coding: utf-8 -*-
"""Ports (interfaces) for external adapters"""

from .action_provider import ActionProvider
from .system_controller import SystemController
from .voice_provider import VoiceProvider
from .web_provider import WebProvider

__all__ = ["VoiceProvider", "ActionProvider", "WebProvider", "SystemController"]
