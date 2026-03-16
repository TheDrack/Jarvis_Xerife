# -*- coding: utf-8 -*-
"""ThoughtLogService — Renderizador ANSI para HUD Visual.
Versão 2026.03: Otimizada para performance e compatibilidade com Enums.
"""
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional
from .thought_log_types import THOUGHT_COLORS, THOUGHT_ICONS


class ThoughtRenderer:
    """Renderiza pensamentos com formatação ANSI para o terminal/HUD."""
    
    def __init__(self, color_enabled: bool = True, show_timestamp: bool = True):
        self.color_enabled = color_enabled
        self.show_timestamp = show_timestamp
        self._reset = "\033[0m"
        self._dim = "\033[2m"
    
    def render(self, thought: Dict[str, Any]) -> str:
        """Renderiza pensamento em string formatada para console."""
        # Extração segura de dados
        raw_type = thought.get("thought_type", "info")
        # Garante que funcione mesmo se for um Enum
        thought_type = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
        
        message = thought.get("message", "")
        timestamp = thought.get("timestamp", datetime.now().isoformat())
        data = thought.get("data", {})
        
        time_str = self._format_timestamp(timestamp)
        color = self._get_color(thought_type)
        icon = self._get_icon(thought_type)
        
        if self.color_enabled:
            formatted = self._build_colored_line(
                time_str, icon, thought_type, message, color
            )
        else:
            formatted = self._build_plain_line(
                time_str, icon, thought_type, message
            )
        
        # Adiciona metadados se existirem
        if data:
            formatted += self._format_data(data)
        
        return formatted
    
    def _format_timestamp(self, timestamp: str) -> str:
        """Formata timestamp (ISO) para exibição curta (HH:MM:SS)."""
        if not self.show_timestamp:
            return ""
        try:
            # Suporte para Z (UTC) ou offsets numéricos
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return "??:??:??"
    
    def _get_color(self, thought_type: str) -> str:
        """Obtém sequência ANSI de cor para o tipo de pensamento."""
        if not self.color_enabled:
            return ""
        return THOUGHT_COLORS.get(thought_type, "")
    
    def _get_icon(self, thought_type: str) -> str:
        """Obtém ícone visual para o tipo de pensamento."""
        return THOUGHT_ICONS.get(thought_type, "•")
    
    def _build_colored_line(self, time_str: str, icon: str,
                            thought_type: str, message: str, color: str) -> str:
        """Constrói linha formatada com cores ANSI."""
        type_tag = f"[{thought_type.upper()}]"
        if time_str:
            return (f"{self._dim}[{time_str}]{self._reset} "
                    f"{color}{icon} {type_tag}{self._reset} {message}")
        return f"{color}{icon} {type_tag}{self._reset} {message}"
    
    def _build_plain_line(self, time_str: str, icon: str,
                          thought_type: str, message: str) -> str:
        """Constrói linha em texto puro (sem ANSI)."""
        type_tag = f"[{thought_type.upper()}]"
        if time_str:
            return f"[{time_str}] {icon} {type_tag} {message}"
        return f"{icon} {type_tag} {message}"
    
    def _format_data(self, data: Dict[str, Any]) -> str:
        """Formata dicionário de dados extras em uma linha truncada."""
        try:
            # Limita a 200 caracteres para não poluir o HUD
            data_str = json.dumps(data, default=str, ensure_ascii=False)
            if len(data_str) > 200:
                data_str = data_str[:197] + "..."
            return f"\n{self._dim}   Data: {data_str}{self._reset}"
        except Exception:
            return ""
    
    def print(self, thought: Dict[str, Any]) -> None:
        """Imprime o pensamento formatado diretamente no stdout com flush."""
        try:
            formatted = self.render(thought)
            sys.stdout.write(formatted + "\n")
            sys.stdout.flush()
        except Exception as e:
            # Fallback silencioso para evitar quebra do sistema por erro de log
            pass
