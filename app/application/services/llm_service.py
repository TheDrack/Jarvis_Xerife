# -*- coding: utf-8 -*-
import logging
import os
from typing import Any, Optional
import httpx

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class LlmService(NexusComponent):
    def __init__(self):
        super().__init__()
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.fallback_model = "llama-3.3-70b-versatile"

    def ask(self, prompt: str, system_instruction: str = "") -> str:
        """Tenta Gemini, se falhar ou cota exceder, usa Groq."""
        
        # Tenta Gemini primeiro
        if self.gemini_key:
            try:
                # Simulando a chamada que você já tem no log
                # Se você usar a lib oficial, o erro 429 cai aqui
                response = self._call_gemini(prompt, system_instruction)
                if response: return response
            except Exception as e:
                if "429" in str(e):
                    logger.warning("⚠️ Cota Gemini excedida (429).")
                else:
                    logger.error(f"❌ Erro Gemini: {e}")

        # Fallback para Groq
        return self._call_groq(prompt, system_instruction)

    def _call_gemini(self, prompt, instr):
        # Aqui deve estar sua lógica atual da lib google-genai
        # Se retornar None ou disparar erro, o ask() fará o fallback
        pass 

    def _call_groq(self, prompt: str, system_instruction: str) -> str:
        logger.info(f"🔄 Acionando Fallback Groq ({self.fallback_model})...")
        if not self.groq_key:
            return "Erro: Sem chaves de API disponíveis."

        try:
            with httpx.Client() as client:
                response = client.post(
                    "https://api.openai.com/v1/chat/completions", # Endpoint Groq/OpenAI compatible
                    headers={"Authorization": f"Bearer {self.groq_key}"},
                    json={
                        "model": self.fallback_model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt}
                        ]
                    },
                    timeout=15.0
                )
                if response.status_code == 200:
                    logger.info("✅ Resposta gerada via Groq.")
                    return response.json()['choices'][0]['message']['content']
                return f"Erro Groq: {response.status_code}"
        except Exception as e:
            logger.error(f"❌ Falha total nos LLMs: {e}")
            return "Desculpe, estou com dificuldades técnicas em todos os meus núcleos de processamento."
