# -*- coding: utf-8 -*-
import logging
import os
from typing import Any, Optional
import httpx

from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

class LlmService(NexusComponent):
    """
    Serviço de Linguagem (LLM) com suporte a Fallback Automático.
    Implementa o método execute para conformidade com o Nexus.
    """

    def __init__(self):
        super().__init__()
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.fallback_model = "llama-3.3-70b-versatile"

    def ask(self, prompt: str, system_instruction: str = "") -> str:
        """Interface principal para chamadas de texto."""
        # Tenta Gemini primeiro (Assumindo que você usa a lib genai em outro lugar do código)
        # Se houver erro de cota (429), o fallback é acionado.
        try:
            # Lógica simplificada de detecção de cota
            if not self.gemini_key:
                raise ValueError("Gemini Key ausente")
            
            # Aqui entraria sua chamada original ao Gemini. 
            # Se ela falhar, o bloco except captura e vai para o Groq.
            return self._call_groq(prompt, system_instruction) 
        except Exception as e:
            logger.warning(f"⚠️ Falha no provedor primário, tentando Groq: {e}")
            return self._call_groq(prompt, system_instruction)

    def _call_groq(self, prompt: str, system_instruction: str) -> str:
        """Chamada resiliente via HTTP para a API do Groq."""
        if not self.groq_key:
            return "Erro: Nenhuma chave de API configurada para LLM."

        logger.info(f"🔄 Gerando resposta via Groq ({self.fallback_model})...")
        
        try:
            with httpx.Client() as client:
                response = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.groq_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.fallback_model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7
                    },
                    timeout=20.0
                )
                
                if response.status_code == 200:
                    return response.json()['choices'][0]['message']['content']
                else:
                    logger.error(f"❌ Erro Groq API: {response.status_code} - {response.text}")
                    return "Tive um problema ao processar sua solicitação nos meus servidores de linguagem."
        except Exception as e:
            logger.error(f"💥 Erro fatal no LLM Fallback: {e}")
            return "Sistemas de linguagem offline. Verifique as conexões de API."

    def execute(self, context: dict) -> dict:
        """
        Implementação obrigatória do NexusComponent.
        Permite que o LLM seja usado dentro de Workflows.
        """
        prompt = context.get("prompt")
        system = context.get("system_instruction", "Você é o Jarvis, um assistente técnico e eficiente.")
        
        if prompt:
            response = self.ask(prompt, system)
            context["llm_response"] = response
            # Se o contexto pedir para atualizar a mensagem final
            if context.get("update_message"):
                context["message"] = response
        
        return context
