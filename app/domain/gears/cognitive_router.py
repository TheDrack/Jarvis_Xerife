# -*- coding: utf-8 -*-
from app.core.nexuscomponent import NexusComponent
import litellm

class CognitiveRouter(NexusComponent):
    """
    Gear de Roteamento: Identifica se a intenção é Automática (Soldado) ou Cognitiva (LLM).
    O método configure é opcional.
    """
    def __init__(self):
        # Padrões caso o configure não seja chamado
        self.maestro_model = "openai/gpt-4o-mini"

    def configure(self, config: dict = None):
        """Permite sobrescrever o modelo via pipeline config."""
        if config:
            self.maestro_model = config.get("maestro_model", self.maestro_model)

    def execute(self, context: dict):
        user_input = context["metadata"].get("user_input", "")
        
        # 1. Bypass rápido para automação (Hardcoded para performance)
        if any(word in user_input.lower() for word in ["digite", "clique", "aperte", "print"]):
            context["metadata"]["marcha"] = "AUTOMACAO"
            return context

        # 2. Decisão de Marcha via LLM
        try:
            response = litellm.completion(
                model=self.maestro_model,
                messages=[{"role": "system", "content": "Responda apenas com: CONVERSA, CODIGO ou INTERNET."},
                          {"role": "user", "content": user_input}]
            )
            marcha = response.choices[0].message.content.strip().upper()
            context["metadata"]["marcha"] = marcha if marcha in ["CODIGO", "INTERNET"] else "CONVERSA"
        except Exception:
            context["metadata"]["marcha"] = "CONVERSA" # Fallback seguro
            
        return context
