from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""AI Gateway Enums - LLM provider and gear definitions."""

from enum import Enum
from typing import Any, Dict, Optional


class LLMProvider(str, Enum):
    """Available LLM providers"""
    GROQ = "groq"
    GEMINI = "gemini"


class GroqGear(str, Enum):
    """Groq Gears (Marchas) - Different Groq models for different use cases"""
    HIGH_GEAR = "high"  # Marcha Alta: Llama-4-Scout or Llama-3.3-70b (default)
    LOW_GEAR = "low"    # Marcha Baixa: Qwen-3-32B or Llama-8B (rate limit fallback)


class AIGatewayEnums(NexusComponent):
    """NexusComponent wrapper that exposes LLMProvider and GroqGear for DI resolution."""

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "success": True,
            "providers": [p.value for p in LLMProvider],
            "gears": [g.value for g in GroqGear],
        }
