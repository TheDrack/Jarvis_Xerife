# -*- coding: utf-8 -*-
"""ThoughtLogService — Renderizador ANSI para HUD Visual."""
import sys
from datetime import datetime
from typing import Dict, Any
from .thought_log_types import THOUGHT_COLORS, THOUGHT_ICONS


class ThoughtRenderer:
    """Renderiza pensamentos com formatação ANSI."""
    
    def __init__(self, color_enabled: bool = True, show_timestamp: bool = True):
        self.color_enabled = color_enabled
        self.show_timestamp = show_timestamp
        self._reset = "\033[0m"
        self._dim = "\033[2m"
    
    def render(self, thought: Dict[str, Any]) -> str:
        """Renderiza pensamento em string formatada."""
        thought_type = thought.get("thought_type", "info")
        message = thought.get("message", "")
        timestamp = thought.get("timestamp", "")
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
        
        if 
            formatted += self._format_data(data)
        
        return formatted
    
    def _format_timestamp(self, timestamp: str) -> str:
        """Formata timestamp para exibição."""
        if not self.show_timestamp:
            return ""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return "??:??:??"
    
    def _get_color(self, thought_type: str) -> str:
        """Obtém cor ANSI para tipo de pensamento."""
        if not self.color_enabled:
            return ""
        return THOUGHT_COLORS.get(thought_type, "")
    
    def _get_icon(self, thought_type: str) -> str:
        """Obtém ícone para tipo de pensamento."""
        return THOUGHT_ICONS.get(thought_type, "•")
    
    def _build_colored_line(self, time_str: str, icon: str,
                            thought_type: str, message: str, color: str) -> str:
        """Constrói linha com cores ANSI."""
        if time_str:
            return (f"{self._dim}[{time_str}]{self._reset} "
                    f"{color}{icon} [{thought_type.upper()}]{self._reset} {message}")
        return f"{color}{icon} [{thought_type.upper()}]{self._reset} {message}"
    
    def _build_plain_line(self, time_str: str, icon: str,
                          thought_type: str, message: str) -> str:
        """Constrói linha sem cores."""
        if time_str:
            return f"[{time_str}] {icon} [{thought_type.upper()}] {message}"
        return f"{icon} [{thought_type.upper()}] {message}"
    
    def _format_data(self, data: Dict[str, Any]) -> str:
        """Formata dados adicionais para exibição."""
        import json
        try:
            data_str = json.dumps(data, default=str)[:200]
            return f"\n{self._dim}   Data: {data_str}{self._reset}"
        except Exception:
            return ""
    
    def print(self, thought: Dict[str, Any]) -> None:
        """Imprime pensamento no console com flush."""
        formatted = self.render(thought)
        print(formatted, file=sys.stdout, flush=True)