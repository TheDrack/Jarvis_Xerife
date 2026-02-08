# -*- coding: utf-8 -*-
"""Agent Service - LLM-based agent logic using Function Calling"""

from typing import Any, Dict, List

from app.domain.models import CommandType


class AgentService:
    """
    Service that defines the agent's capabilities using Function Calling.
    Maps ActionProvider methods to function definitions for LLM.
    """

    @staticmethod
    def get_function_declarations() -> List[Dict[str, Any]]:
        """
        Get function declarations for the LLM to use.
        These represent the ActionProvider capabilities.

        Returns:
            List of function declarations in Gemini function calling format
        """
        return [
            {
                "name": "type_text",
                "description": "Digita texto usando o teclado. Use esta função quando o usuário pedir para escrever ou digitar algo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "O texto a ser digitado",
                        }
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "press_key",
                "description": "Pressiona uma tecla do teclado. Use para comandos como 'aperte enter', 'pressione tab', etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Nome da tecla a ser pressionada (ex: 'enter', 'tab', 'escape', 'space')",
                        }
                    },
                    "required": ["key"],
                },
            },
            {
                "name": "open_browser",
                "description": "Abre o navegador web usando um atalho de teclado. Use quando o usuário pedir para abrir o navegador ou internet.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "open_url",
                "description": "Abre uma URL específica no navegador. Use quando o usuário mencionar um site ou endereço web.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "A URL a ser aberta (será adicionado https:// se necessário)",
                        }
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "search_on_page",
                "description": "Procura texto em uma página web aberta. Use quando o usuário pedir para procurar ou clicar em algo na página.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_text": {
                            "type": "string",
                            "description": "O texto a ser procurado na página",
                        }
                    },
                    "required": ["search_text"],
                },
            },
            {
                "name": "report_issue",
                "description": "Reporta um problema ou cria uma issue no GitHub. Use quando o usuário pedir para reportar, criar issue ou relatar um bug.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "issue_description": {
                            "type": "string",
                            "description": "Descrição do problema a ser reportado",
                        }
                    },
                    "required": ["issue_description"],
                },
            },
        ]

    @staticmethod
    def map_function_to_command_type(function_name: str) -> CommandType:
        """
        Map a function name to a CommandType.

        Args:
            function_name: Name of the function called by the LLM

        Returns:
            Corresponding CommandType
        """
        function_to_command = {
            "type_text": CommandType.TYPE_TEXT,
            "press_key": CommandType.PRESS_KEY,
            "open_browser": CommandType.OPEN_BROWSER,
            "open_url": CommandType.OPEN_URL,
            "search_on_page": CommandType.SEARCH_ON_PAGE,
            "report_issue": CommandType.REPORT_ISSUE,
        }
        return function_to_command.get(function_name, CommandType.UNKNOWN)

    @staticmethod
    def get_system_instruction() -> str:
        """
        Get the system instruction for the LLM.
        Defines the personality and behavior of the "Xerife" assistant as an orchestrator.

        Returns:
            System instruction text
        """
        return """Xerife - Engenheiro de Campo. Direto, técnico, zero fluff.

PROIBIDO:
- Frases genéricas ("Como um assistente virtual...")
- Explicações repetitivas
- Saudações desnecessárias
- Textos longos

OBRIGATÓRIO:
- Respostas em 1 frase ou lista de máx. 3 itens
- Técnico e objetivo
- Foco em ação imediata

Ações:
- Coordenar dispositivos (celular, PC, IoT)
- Gerenciar recursos físicos
- Reportar issues no GitHub

Diretrizes:
- GPS: priorizar dispositivos <1km
- Confirmação: se alvo >50km

Exemplos:
- "tire selfie" -> câmera atual
- "ligue TV" -> IoT local
- "reporte botão quebrado" -> use report_issue"""
