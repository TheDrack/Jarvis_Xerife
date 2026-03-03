# -*- coding: utf-8 -*-
"""
Intent Processor Dinâmico - O Roteador Universal do Jarvis.
Delega a execução para componentes descobertos dinamicamente pelo Nexus.
"""

import logging
from typing import Any, Dict
from app.core.nexus import nexus, CloudMock
from app.core.nexuscomponent import NexusComponent
from app.domain.models import CommandType

logger = logging.getLogger(__name__)

class IntentProcessor(NexusComponent):
    """
    Processador de Intenções: Transforma um Intent em uma ação real,
    buscando o executor correspondente no repositório.
    """

    def execute(self, context: dict) -> Any:
        """
        Ponto de entrada para o AssistantService.
        Resolve o executor dinamicamente baseado no CommandType.
        """
        intent = context.get("intent")
        if not intent:
            logger.warning("⚠️ [PROCESSOR] Recebida intenção nula.")
            return "Erro: Intenção não fornecida ao processador."

        # 1. Extração do ID do componente alvo (Ex: CommandType.TYPE_TEXT -> 'type_text')
        cmd_type = getattr(intent, 'command_type', CommandType.UNKNOWN)
        
        # Normaliza o ID para busca no Nexus (snake_case do Enum)
        if hasattr(cmd_type, 'name'):
            target_id = cmd_type.name.lower()
        else:
            target_id = str(cmd_type).split('.')[-1].lower()

        logger.info(f"🎯 [PROCESSOR] Buscando executor para: '{target_id}'")

        # 2. RESOLUÇÃO DINÂMICA VIA NEXUS (A busca física no repositório)
        # Se você criou 'app/capabilities/sync_to_drive.py', o Nexus o encontrará aqui.
        executor = nexus.resolve(target_id)

        # 3. Execução do Executor Encontrado
        if executor and not isinstance(executor, CloudMock):
            try:
                logger.info(f"⚡ [PROCESSOR] Executando componente dinâmico: {target_id}")
                
                # Prepara parâmetros (garante que seja um dict)
                params = getattr(intent, 'parameters', {})
                if not isinstance(params, dict):
                    params = {"data": params}

                # Executa o componente (deve ter método execute)
                result = executor.execute(params)
                
                # Normalização do retorno para string
                if isinstance(result, dict):
                    return result.get("message", "Comando executado sem mensagem de retorno.")
                return str(result)
            
            except Exception as e:
                logger.error(f"💥 [PROCESSOR] Falha ao executar {target_id}: {e}")
                return f"Erro na execução do componente {target_id}: {str(e)}"

        # 4. FALLBACK PARA IA (Se o executor físico não existir ou for Mock)
        logger.info(f"🤖 [PROCESSOR] Executor '{target_id}' não encontrado. Delegando para LLM...")
        raw_text = getattr(intent, 'raw_input', str(intent))
        return self._process_with_llm(raw_text)

    def _process_with_llm(self, text: str) -> str:
        """
        Utiliza o LLM (Gemini/Groq) como cérebro de reserva.
        """
        try:
            llm = nexus.resolve("llm_service") or nexus.resolve("ai_gateway")
            if llm:
                # Se for o gateway, ele usa o método generate ou chat
                return llm.generate(text) if hasattr(llm, 'generate') else str(llm.chat(text))
            return "IA indisponível no momento para processar este comando."
        except Exception as e:
            logger.error(f"❌ [PROCESSOR] Erro no fallback de IA: {e}")
            return "Falha crítica na comunicação com o cérebro de reserva (LLM)."

