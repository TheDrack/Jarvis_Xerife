# -*- coding: utf-8 -*-
"""LLM Service - Wraps Google Gemini AI with Groq Fallback"""

import logging
import os
from typing import Any, Dict, Optional

from google import genai
from groq import Groq  # Já instalado via pip conforme logs

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class LlmService(NexusComponent):
    """
    Serviço de IA que usa o Google Gemini como primário e Groq como fallback.
    Garante que o JARVIS nunca fique sem resposta por falta de cota.
    """

    def __init__(self) -> None:
        super().__init__()
        # Configuração Gemini
        self.gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_client = genai.Client(api_key=self.gemini_key) if self.gemini_key else None
        self.model_name = "gemini-2.0-flash"

        # Configuração Fallback (Groq)
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.groq_client = Groq(api_key=self.groq_key) if self.groq_key else None
        self.fallback_model = "llama-3.3-70b-versatile"

        if not self.gemini_key and not self.groq_key:
            logger.error("Nenhuma chave de IA configurada (Gemini ou Groq).")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        text = (context or {}).get("text", "")
        response = self.generate(text) if text else ""
        return {"result": response, "success": bool(response)}

    def generate(self, prompt: str) -> str:
        """Tenta Gemini, se falhar (cota/erro), tenta Groq."""
        
        # 1. Tentativa Primária: Gemini
        if self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                if response.candidates and response.candidates[0].content.parts:
                    return response.candidates[0].content.parts[0].text.strip()
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning("⚠️ Cota Gemini excedida. Acionando Fallback Groq...")
                else:
                    logger.error(f"Erro Gemini: {e}")

        # 2. Tentativa de Contingência: Groq
        if self.groq_client:
            try:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.fallback_model,
                )
                logger.info(f"✅ Resposta gerada via Fallback ({self.fallback_model})")
                return chat_completion.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Erro Crítico: Gemini e Groq falharam. Detalhe Groq: {e}")

        return "Desculpe, meus sistemas de IA estão temporariamente sobrecarregados. Por favor, tente em alguns instantes."
