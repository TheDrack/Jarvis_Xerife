# -*- coding: utf-8 -*-
"""ThoughtLogService — Tipos e Constantes para Thought Stream.
Versão 2026.03: Revisada para consistência de tipos.
"""
from enum import Enum

class ThoughtType(str, Enum):
    """Tipos de pensamento para formatação visual e lógica de processamento."""
    PLANNING = "planning"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    ERROR = "error"
    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"


# Cores ANSI por tipo de pensamento (Reset: \033[0m deve ser usado no logger)
THOUGHT_COLORS = {
    ThoughtType.PLANNING: "\033[96m\033[1m",    # Cyan brilhante
    ThoughtType.ACTION: "\033[93m\033[1m",      # Amarelo brilhante
    ThoughtType.OBSERVATION: "\033[92m",        # Verde
    ThoughtType.REFLECTION: "\033[95m",         # Magenta
    ThoughtType.ERROR: "\033[91m\033[1m",       # Vermelho brilhante
    ThoughtType.SUCCESS: "\033[92m\033[1m",     # Verde brilhante
    ThoughtType.WARNING: "\033[93m",            # Amarelo
    ThoughtType.INFO: "\033[37m\033[2m",        # Branco dim
}

# Ícones por tipo de pensamento para HUD e Logs
THOUGHT_ICONS = {
    ThoughtType.PLANNING: "🧠",
    ThoughtType.ACTION: "⚡",
    ThoughtType.OBSERVATION: "👁️",
    ThoughtType.REFLECTION: "💭",
    ThoughtType.ERROR: "❌",
    ThoughtType.SUCCESS: "✅",
    ThoughtType.WARNING: "⚠️",
    ThoughtType.INFO: "ℹ️",
}

# Configurações padrão do Stream de Pensamento
DEFAULT_CONFIG = {
    "enabled": True,
    "max_observation_length": 500,
    "max_history": 100,
    "stream_to_console": True,
    "persist_to_db": True,
    "color_enabled": True,
    "show_timestamp": True,
}
