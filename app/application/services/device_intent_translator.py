# -*- coding: utf-8 -*-
"""Device Intent Translator — Traduz linguagem natural para comandos Android.
PASSO 3: Camada de tradução entre fala do usuário e comandos de sistema.
"""
import logging
import re
from typing import Dict, Any, Optional, Tuple
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class DeviceIntentTranslator(NexusComponent):
    """
    Tradutor de comandos de voz para intents do MacroDroid.
    
    Mapeamento:
    - "lanterna" → action: 'flashlight', data: {'state': 'toggle'}
    - "modo silencioso" → action: 'silent_mode', data: {'enabled': True}
    - "abrir instagram" → action: 'open_app', data: {'package': 'com.instagram.android'}
    """
    
    # Mapeamento de termos gatilho → comandos
    COMMAND_MAP: Dict[str, Dict[str, Any]] = {
        # Controle de hardware
        "lanterna": {"action": "flashlight", "data": {"state": "toggle"}},
        "flash": {"action": "flashlight", "data": {"state": "toggle"}},
        "luz": {"action": "flashlight", "data": {"state": "toggle"}},
        
        # Modo silencioso
        "silencioso": {"action": "silent_mode", "data": {"enabled": True}},
        "mudo": {"action": "silent_mode", "data": {"enabled": True}},
        "vibrar": {"action": "vibrate_mode", "data": {}},
        
        # Volume
        "volume máximo": {"action": "set_volume", "data": {"stream": "media", "level": 100}},
        "volume mínimo": {"action": "set_volume", "data": {"stream": "media", "level": 0}},
        
        # WiFi
        "ligar wifi": {"action": "wifi", "data": {"enabled": True}},
        "desligar wifi": {"action": "wifi", "data": {"enabled": False}},
        
        # Bluetooth
        "ligar bluetooth": {"action": "bluetooth", "data": {"enabled": True}},
        "desligar bluetooth": {"action": "bluetooth", "data": {"enabled": False}},
        
        # Apps comuns
        "instagram": {"action": "open_app", "data": {"package": "com.instagram.android"}},
        "whatsapp": {"action": "open_app", "data": {"package": "com.whatsapp"}},
        "telegram": {"action": "open_app", "data": {"package": "org.telegram.messenger"}},        "youtube": {"action": "open_app", "data": {"package": "com.google.android.youtube"}},
        "spotify": {"action": "open_app", "data": {"package": "com.spotify.music"}},
        "chrome": {"action": "open_app", "data": {"package": "com.android.chrome"}},
        
        # Sistema
        "bloquear tela": {"action": "lock_screen", "data": {}},
        "tirar print": {"action": "screenshot", "data": {}},
        "print": {"action": "screenshot", "data": {}},
    }
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return True
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point via Nexus DI."""
        ctx = context or {}
        user_input = ctx.get("user_input", "")
        
        if not user_input:
            return {"success": False, "error": "user_input obrigatório"}
        
        return self.translate(user_input)
    
    def translate(self, user_input: str) -> Dict[str, Any]:
        """
        PASSO 3: Traduz entrada do usuário para DeviceIntent.
        
        Returns:
            Dict com:
            - is_device_command: bool (se é comando de dispositivo)
            - action: str (ação para MacroDroid)
            - data: dict (dados extras)
            - confidence: float (0.0-1.0)
        """
        user_input = user_input.lower().strip()
        
        # Remove wake word se presente
        wake_words = ["xerife", "jarvis", "ok jarvis"]
        for wake in wake_words:
            user_input = user_input.replace(wake, "").strip()
        
        # Busca comando no mapa
        for keyword, command in self.COMMAND_MAP.items():
            if keyword in user_input:
                logger.info(f"🎯 [Translator] Comando detectado: '{keyword}'")
                return {
                    "is_device_command": True,
                    "action": command["action"],
                    "data": command.get("data", {}),                    "confidence": 0.95,
                    "matched_keyword": keyword
                }
        
        # Padrão para abrir apps genéricos
        app_match = re.search(r'abrir\s+(\w+)', user_input)
        if app_match:
            app_name = app_match.group(1)
            return {
                "is_device_command": True,
                "action": "open_app",
                "data": {"package": f"com.{app_name}.android"},
                "confidence": 0.7,
                "matched_keyword": f"abrir {app_name}"
            }
        
        # Não é comando de dispositivo
        return {
            "is_device_command": False,
            "action": None,
            "data": None,
            "confidence": 0.0
        }
    
    def is_device_command(self, user_input: str) -> bool:
        """Check rápido se entrada é comando de dispositivo."""
        result = self.translate(user_input)
        return result.get("is_device_command", False)
    
    def add_command(self, keyword: str, action: str, data: Dict[str, Any]) -> None:
        """Adiciona comando customizado ao mapa (runtime)."""
        self.COMMAND_MAP[keyword.lower()] = {
            "action": action,
            "data": data
        }
        logger.info(f"📝 [Translator] Comando '{keyword}' adicionado")


# Compatibilidade
DeviceTranslator = DeviceIntentTranslator