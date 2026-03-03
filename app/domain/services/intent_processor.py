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

        # 1. Extração do ID do componente alvo
        cmd_type = getattr(intent, 'command_type', CommandType.UNKNOWN)

        # Normaliza o ID para busca no Nexus
        if hasattr(cmd_type, 'name'):
            target_id = cmd_type.name.lower()
        else:
            target_id = str(cmd_type).split('.')[-1].lower()

        logger.info(f"🎯 [PROCESSOR] Buscando executor para: '{target_id}'")

        # 2. RESOLUÇÃO DINÂMICA VIA NEXUS
        executor = nexus.resolve(target_id)

        # 3. Execução do Executor Encontrado (Se não for Mock)
        if executor and not isinstance(executor, CloudMock):
            try:
                logger.info(f"⚡ [PROCESSOR] Executando componente dinâmico: {target_id}")

                params = getattr(intent, 'parameters', {})
                if not isinstance(params, dict):
                    params = {"data": params}

                result = executor.execute(params)

                if isinstance(result, dict):
                    return result.get("message", "Comando executado com sucesso.")
                return str(result)

            except Exception as e:
                logger.error(f"💥 [PROCESSOR] Falha ao executar {target_id}: {e}")
                # Fallback para IA em caso de erro no executor físico
        
        # 4. FALLBACK PARA IA (Executores desconhecidos, Mocks ou Falhas)
        logger.info(f"🤖 [PROCESSOR] Redirecionando para LLM (Motivo: {target_id})...")
        raw_text = getattr(intent, 'raw_input', str(intent))
        return self._process_with_llm(raw_text)

    def _process_with_llm(self, text: str) -> str:
        """Utiliza o LLM como cérebro de reserva."""
        try:
            # Tenta resolver o serviço de IA
            llm = nexus.resolve("llm_service") or nexus.resolve("ai_gateway")
            
            if llm and not isinstance(llm, CloudMock):
                # Tenta os métodos conhecidos por ordem de preferência
                if hasattr(llm, 'chat'):
                    return llm.chat(text)
                elif hasattr(llm, 'ask'):
                    return llm.ask(text)
                elif hasattr(llm, 'generate'):
                    return llm.generate(text)
                elif hasattr(llm, 'execute'):
                    res = llm.execute({"prompt": text})
                    return res.get("message") or res.get("llm_response", str(res))
            
            return "IA indisponível no momento para processar este comando."
        except Exception as e:
            logger.error(f"❌ [PROCESSOR] Erro no fallback de IA: {e}")
            return "Falha crítica na comunicação com o cérebro de reserva (LLM)."
