# -*- coding: utf-8 -*-
from app.core.nexus import NexusComponent


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
        metadata = context.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            raise TypeError("context['metadata'] must be a dict")

        user_input = metadata.get("user_input", "")

        # 1. Bypass rápido para automação (Hardcoded para performance)
        if any(word in user_input.lower() for word in ["digite", "clique", "aperte", "print"]):
            metadata["marcha"] = "AUTOMACAO"
            return context

        # 2. Decisão de Marcha via LLM. LiteLLM é opcional para este gear:
        # sem o provider instalado, o fallback mantém o pipeline utilizável.
        try:
            import litellm

            response = litellm.completion(
                model=self.maestro_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Responda apenas com: CONVERSA, CODIGO ou INTERNET.",
                    },
                    {"role": "user", "content": user_input},
                ],
            )
            marcha = response.choices[0].message.content.strip().upper()
            metadata["marcha"] = (
                marcha if marcha in ["CODIGO", "INTERNET"] else "CONVERSA"
            )
        except Exception:
            metadata["marcha"] = "CONVERSA"  # Fallback seguro

        return context
