# -*- coding: utf-8 -*-
"""Intent Processor Dinâmico - Delega execução via Nexus"""

import logging
from typing import Any
from app.core.nexus import nexus, CloudMock
from app.core.nexuscomponent import NexusComponent
from app.domain.models import CommandType

logger = logging.getLogger(__name__)

class IntentProcessor(NexusComponent):
    def execute(self, context: dict) -> Any:
        intent = context.get("intent")
        if not intent: return "Erro: Intenção nula."

        # Pega o tipo do comando (ex: SYNC_TO_DRIVE)
        cmd_type = intent.command_type if hasattr(intent, 'command_type') else CommandType.UNKNOWN
        
        # Converte o enum SYNC_TO_DRIVE para o ID do componente no Nexus: "sync_to_drive"
        target_id = cmd_type.name.lower() if hasattr(cmd_type, 'name') else str(cmd_type).lower()

        # TENTA RESOLUÇÃO DINÂMICA VIA NEXUS
        # O Nexus vai varrer o projeto procurando por sync_to_drive.py
        executor = nexus.resolve(target_id)

        if executor and not isinstance(executor, CloudMock):
            logger.info(f"⚡ Executando componente dinâmico: {target_id}")
            result = executor.execute(intent.parameters)
            return result.get("message") if isinstance(result, dict) else result

        # Fallback para LLM se o executor não for encontrado ou for Mock em Cloud
        return self._process_with_llm(intent.raw_input if hasattr(intent, 'raw_input') else str(intent))

    def _process_with_llm(self, text: str) -> str:
        llm = nexus.resolve("llm_service")
        return llm.generate(text) if llm else "IA indisponível."
