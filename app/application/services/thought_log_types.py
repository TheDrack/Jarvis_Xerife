# -*- coding: utf-8 -*-
"""ThoughtLogService — Tipos e Constantes ANSI.

Define cores, ícones e tipos de pensamento para o HUD visual.
"""

class ANSI:
    """Códigos ANSI para formatação de terminal."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    
    # Cores de texto
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Cores brilhantes
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"


class ThoughtType:
    """Tipos de pensamento para formatação visual."""
    PLANNING = "planning"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    ERROR = "error"
    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"


# Mapeamento de cores por tipo
THOUGHT_COLORS = {
    ThoughtType.PLANNING: f"{ANSI.BRIGHT_CYAN}{ANSI.BOLD}",
    ThoughtType.ACTION: f"{ANSI.BRIGHT_YELLOW}{ANSI.BOLD}",
    ThoughtType.OBSERVATION: f"{ANSI.BRIGHT_GREEN}",
    ThoughtType.REFLECTION: f"{ANSI.BRIGHT_MAGENTA}",
    ThoughtType.ERROR: f"{ANSI.BRIGHT_RED}{ANSI.BOLD}",
    ThoughtType.SUCCESS: f"{ANSI.BRIGHT_GREEN}{ANSI.BOLD}",
    ThoughtType.WARNING: f"{ANSI.BRIGHT_YELLOW}",
    ThoughtType.INFO: f"{ANSI.WHITE}{ANSI.DIM}",
}

# Ícones por tipo
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

# Configurações padrão
DEFAULT_CONFIG = {
    "enabled": True,
    "max_observation_length": 500,
    "max_history": 100,
    "stream_to_console": True,
    "persist_to_db": False,
    "show_timestamp": True,
    "color_enabled": True,
}