# -*- coding: utf-8 -*-
"""
Command Interpreter - Pure business logic for interpreting user commands.
Integrado ao ecossistema Nexus para resolução dinâmica.
"""

from app.core.nexuscomponent import NexusComponent
from app.domain.models import CommandType, Intent
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class CommandInterpreter(NexusComponent):
    """
    Interpreta comandos de texto bruto em Intents estruturados.
    Lógica pura, sem dependências de hardware ou frameworks externos.
    """

    def __init__(self, wake_word: str = None):
        """
        Inicializa o interpretador de comandos.
        
        Args:
            wake_word: A palavra de ativação para filtrar dos comandos.
                       Se None, busca 'xerife' ou a config do sistema.
        """
        super().__init__()
        self.wake_word = wake_word or getattr(settings, "wake_word", "xerife").lower()
        
        # Mapeamento de padrões para tipos de comando
        self._command_patterns = {
            # GitHub workflow / flow commands
            "rodar workflow": CommandType.RUN_WORKFLOW,
            "executar workflow": CommandType.RUN_WORKFLOW,
            "acionar workflow": CommandType.RUN_WORKFLOW,
            "rodar fluxo": CommandType.RUN_WORKFLOW,
            "executar fluxo": CommandType.RUN_WORKFLOW,
            "acionar fluxo": CommandType.RUN_WORKFLOW,
            "workflow": CommandType.RUN_WORKFLOW,
            "fluxo": CommandType.RUN_WORKFLOW,
            # Standard commands
            "escreva": CommandType.TYPE_TEXT,
            "digite": CommandType.TYPE_TEXT,
            "aperte": CommandType.PRESS_KEY,
            "pressione": CommandType.PRESS_KEY,
            "internet": CommandType.OPEN_BROWSER,
            "navegador": CommandType.OPEN_BROWSER,
            "site": CommandType.OPEN_URL,
            "abrir": CommandType.OPEN_URL,
            "clicar em": CommandType.SEARCH_ON_PAGE,
            "procurar": CommandType.SEARCH_ON_PAGE,
            "reporte": CommandType.REPORT_ISSUE,
            "reportar": CommandType.REPORT_ISSUE,
            "issue": CommandType.REPORT_ISSUE,
        }

    def execute(self, context: dict) -> Intent:
        """
        Ponto de entrada para o AssistantService.
        
        Args:
            context: Dicionário contendo pelo menos a chave 'text'.
        """
        if not context or not isinstance(context, dict):
            logger.warning("⚠️ [INTERPRETER] Contexto inválido recebido.")
            return self.interpret("")
            
        text = context.get("text", "")
        return self.interpret(text)

    def interpret(self, raw_input: str) -> Intent:
        """
        Converte entrada bruta em um objeto Intent estruturado.
        """
        if not raw_input:
            return Intent(command_type=CommandType.UNKNOWN, parameters={}, raw_input="", confidence=0.0)

        # Normalização
        command = raw_input.lower().strip()

        # Remoção da Wake Word
        if self.wake_word in command:
            command = command.replace(self.wake_word, "").strip()
            # Preserva casing do original para parâmetros sensíveis
            raw_input_lower = raw_input.lower()
            wake_pos = raw_input_lower.find(self.wake_word)
            if wake_pos != -1:
                raw_input = raw_input[wake_pos + len(self.wake_word):].strip()

        # Busca por padrões
        for pattern, command_type in self._command_patterns.items():
            if pattern in command:
                # Extração de parâmetros
                param = command.replace(pattern, "", 1).strip()

                # Preservação de Case para Report de Issues
                if command_type == CommandType.REPORT_ISSUE:
                    raw_lower = raw_input.lower()
                    pattern_pos = raw_lower.find(pattern)
                    if pattern_pos != -1:
                        param_start = pattern_pos + len(pattern)
                        param = raw_input[param_start:].strip()

                parameters = self._build_parameters(command_type, param, command)

                return Intent(
                    command_type=command_type,
                    parameters=parameters,
                    raw_input=raw_input,
                    confidence=1.0,
                )

        # Comando não reconhecido
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": command},
            raw_input=raw_input,
            confidence=0.5,
        )

    def _build_parameters(self, command_type: CommandType, param: str, full_command: str) -> dict:
        """Constrói o dicionário de parâmetros baseado no tipo."""
        handlers = {
            CommandType.TYPE_TEXT: lambda: {"text": param},
            CommandType.PRESS_KEY: lambda: {"key": param},
            CommandType.OPEN_BROWSER: lambda: {},
            CommandType.OPEN_URL: lambda: {"url": param if param.startswith("http") else f"https://{param}"},
            CommandType.SEARCH_ON_PAGE: lambda: {"search_text": param},
            CommandType.REPORT_ISSUE: lambda: {"issue_description": param, "context": full_command},
            CommandType.RUN_WORKFLOW: lambda: {"workflow_name": param, "event_type": "jarvis_order"}
        }
        
        return handlers.get(command_type, lambda: {"param": param})()

    def is_exit_command(self, raw_input: str) -> bool:
        exit_keywords = ["fechar", "sair", "encerrar", "tchau"]
        return any(k in raw_input.lower() for k in exit_keywords)

    def is_cancel_command(self, raw_input: str) -> bool:
        cancel_keywords = ["cancelar", "parar", "stop"]
        return any(k in raw_input.lower() for k in cancel_keywords)
