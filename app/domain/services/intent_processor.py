# -*- coding: utf-8 -*-
"""Intent Processor - Pure business logic for processing intents"""

import logging
from datetime import datetime
from typing import Optional, Any, Dict

from app.domain.models import Command, CommandType, Intent, Response
from app.core.nexuscomponent import NexusComponent
from app.core.nexus import nexus

logger = logging.getLogger(__name__)

class IntentProcessor(NexusComponent):
    """
    Processes intents and creates commands.
    Conecta a intenção do usuário à ação final ou resposta da IA.
    """

    def __init__(self):
        super().__init__()
        # Resolve o serviço de IA para respostas de conversação
        self.llm = nexus.resolve("llm_service")

    def execute(self, context: dict) -> Any:
        """
        Ponto de entrada chamado pelo AssistantService.
        Resolve o erro 'Cristalizador' processando o contexto recebido.
        """
        intent = context.get("intent")
        
        if not intent:
            return "Erro: Intenção não encontrada no contexto."

        # Se for uma Intent estruturada do domínio
        if hasattr(intent, 'command_type'):
            # Se for uma dúvida ou comando desconhecido, usamos o LLM
            if intent.command_type == CommandType.UNKNOWN:
                return self._process_with_llm(intent.raw_input)
            
            # Se for um comando de ação (Digitar, Abrir URL, etc)
            return self.create_command(intent, context)

        # Fallback para texto bruto
        return self._process_with_llm(str(intent))

    def _process_with_llm(self, text: str) -> str:
        """Gera resposta via Gemini se disponível"""
        if self.llm:
            try:
                return self.llm.generate(text)
            except Exception as e:
                logger.error(f"Erro no LLM: {e}")
                return f"Desculpe, tive um problema técnico: {str(e)}"
        return f"Recebi sua mensagem: '{text}', mas meu motor de IA não está carregado."

    def create_command(self, intent: Intent, context: Optional[dict] = None) -> Command:
        """Cria um objeto Command pronto para execução"""
        return Command(
            intent=intent,
            timestamp=datetime.now().isoformat(),
            context=context or {},
        )

    def validate_intent(self, intent: Intent) -> Response:
        """Valida a intenção antes do processamento"""
        if intent.command_type == CommandType.UNKNOWN:
            return Response(
                success=False,
                message=f"Comando desconhecido: {intent.raw_input}",
                error="UNKNOWN_COMMAND",
            )
        return self._validate_parameters(intent)

    def _validate_parameters(self, intent: Intent) -> Response:
        """Valida parâmetros obrigatórios para cada tipo de comando"""
        params = intent.parameters
        if intent.command_type == CommandType.TYPE_TEXT and not params.get("text"):
            return Response(success=False, message="Texto é obrigatório", error="MISSING_PARAMETER")
        
        if intent.command_type == CommandType.OPEN_URL and not params.get("url"):
            return Response(success=False, message="URL é obrigatória", error="MISSING_PARAMETER")

        return Response(success=True, message="Parâmetros válidos")

    def should_provide_feedback(self, command_type: CommandType) -> bool:
        """Define se o comando deve ter resposta por voz/texto"""
        silent_commands = {CommandType.TYPE_TEXT, CommandType.PRESS_KEY}
        return command_type not in silent_commands
