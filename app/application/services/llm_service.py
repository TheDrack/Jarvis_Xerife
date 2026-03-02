# -*- coding: utf-8 -*-
"""LLM Service - Wraps Google Gemini AI for conversational responses"""

import logging
import os
from typing import Any, Dict, Optional

from google import genai

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)


class LlmService(NexusComponent):
    """
    Serviço de IA que usa o Google Gemini para gerar respostas conversacionais.
    Utilizado pelo IntentProcessor para responder a comandos desconhecidos.
    """

    def __init__(self) -> None:
        super().__init__()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be configured")
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.0-flash"

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """NexusComponent entry point — delegates to generate() using context text."""
        text = (context or {}).get("text", "")
        response = self.generate(text) if text else ""
        return {"result": response, "success": bool(response)}

    def generate(self, prompt: str) -> str:
        """
        Gera uma resposta da IA para o prompt fornecido.

        Args:
            prompt: Texto de entrada do utilizador.

        Returns:
            Resposta gerada pelo modelo Gemini.
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            return part.text.strip()
            return ""
        except Exception as e:
            logger.error(f"Erro ao gerar resposta do LLM para prompt '{prompt[:80]}...': {e}")
            return "Desculpe, ocorreu um erro ao processar sua solicitação. Tente novamente mais tarde."
