# -*- coding: utf-8 -*-
"""Intent Processor - Pure business logic with safe LLM handling"""

import logging
from datetime import datetime
from typing import Optional, Any, Dict

from app.domain.models import Command, CommandType, Intent, Response
from app.core.nexuscomponent import NexusComponent
from app.core.nexus import nexus

logger = logging.getLogger(__name__)

class IntentProcessor(NexusComponent):
    def __init__(self):
        super().__init__()
        # Inicialização tardia para garantir que o Nexus já carregou o serviço
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = nexus.resolve("llm_service")
        return self._llm

    def execute(self, context: dict) -> Any:
        intent = context.get("intent")
        if not intent:
            return "Erro: Intenção não identificada."

        # Se for um objeto Intent (do parser)
        if hasattr(intent, 'command_type'):
            if intent.command_type == CommandType.UNKNOWN:
                return self._process_with_llm(intent.raw_input)
            return self.create_command(intent, context)

        # Se for apenas texto (fallback direto)
        return self._process_with_llm(str(intent))

    def _process_with_llm(self, text: str) -> str:
        """Gera resposta via LLM Service (com suporte a fallback interno)"""
        service = self.llm
        if service:
            try:
                return service.generate(text)
            except Exception as e:
                logger.error(f"Falha fatal no processamento LLM: {e}")
                return "Estou com dificuldades técnicas para processar isso agora."
        
        return f"Recebi: '{text}', mas meu módulo de inteligência não foi carregado."

    def create_command(self, intent: Intent, context: Optional[dict] = None) -> Command:
        return Command(
            intent=intent,
            timestamp=datetime.now().isoformat(),
            context=context or {},
        )
