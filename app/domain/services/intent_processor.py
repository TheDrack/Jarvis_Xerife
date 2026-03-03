# -*- coding: utf-8 -*-
import logging
from typing import Any
from app.core.nexus import nexus, CloudMock
from app.core.nexuscomponent import NexusComponent
from app.domain.models import CommandType

logger = logging.getLogger(__name__)

class IntentProcessor(NexusComponent):
    """
    Processador de Intenções: Roteia para comandos locais ou delega para LLM.
    """

    def execute(self, context: dict) -> Any:
        intent_obj = context.get("intent")
        if not intent_obj:
            return "Erro: Objeto de intenção não encontrado no contexto."

        # 1. Identificação do Tipo de Comando
        cmd_type = getattr(intent_obj, 'command_type', CommandType.UNKNOWN)
        
        # Extrai o nome do comando (ex: 'sync_to_drive', 'type_text', etc)
        if hasattr(cmd_type, 'name'):
            target_id = cmd_type.name.lower()
        else:
            target_id = str(cmd_type).split('.')[-1].lower()

        raw_text = getattr(intent_obj, 'raw_input', str(intent_obj))

        # 2. FILTRO DE ATALHO: Se for unknown, não gaste energia procurando no Nexus
        if target_id == "unknown":
            logger.info("🤖 [PROCESSOR] Nenhuma intenção técnica detectada. Direcionando para LLM.")
            return self._process_with_llm(raw_text)

        # 3. RESOLUÇÃO DE COMANDO TÉCNICO
        logger.info(f"🎯 [PROCESSOR] Buscando executor para: '{target_id}'")
        executor = nexus.resolve(target_id)

        if executor and not isinstance(executor, CloudMock):
            try:
                params = getattr(intent_obj, 'parameters', {})
                if not isinstance(params, dict): params = {"data": params}
                
                result = executor.execute(params)
                
                if isinstance(result, dict):
                    return result.get("message", "Comando executado com sucesso.")
                return str(result)
            except Exception as e:
                logger.error(f"💥 [PROCESSOR] Erro ao executar {target_id}: {e}")

        # 4. FALLBACK FINAL
        return self._process_with_llm(raw_text)

    def _process_with_llm(self, text: str) -> str:
        """Delegação direta para o cérebro de reserva."""
        try:
            llm = nexus.resolve("llm_service")
            if llm and not isinstance(llm, CloudMock):
                # Tenta métodos conhecidos para garantir resposta
                for method in ['chat', 'ask', 'generate']:
                    if hasattr(llm, method):
                        return getattr(llm, method)(text)
            return "Não consegui processar seu pedido e meu núcleo de IA está offline."
        except Exception as e:
            logger.error(f"❌ [PROCESSOR] Erro fatal no LLM: {e}")
            return "Falha crítica de comunicação interna."
