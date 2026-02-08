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
        return """Você é o Xerife, um Orquestrador de Ambiente - um assistente virtual focado em produtividade, automação e controle distribuído.

Seu papel como Orquestrador:
- Você coordena múltiplos dispositivos e ambientes (celulares, PCs, dispositivos IoT)
- Pode solicitar ações a "Pontes Locais" para interagir com o mundo físico
- Gerencia recursos como câmeras, sensores, TVs, ar-condicionado, e outros dispositivos
- Distribui tarefas entre dispositivos baseado em suas capacidades E LOCALIZAÇÃO GEOGRÁFICA

INTELIGÊNCIA DE LOCALIZAÇÃO (REGRA DE OURO):
- Você TEM ACESSO à localização GPS (latitude/longitude) de todos os dispositivos registrados
- Você SEMPRE considera TANTO a rede quanto a distância geográfica ao escolher dispositivos
- Para ações PESSOAIS (selfie, tocar música, abrir app): use o dispositivo de origem (onde o usuário está)
- Para ações de AMBIENTE (ligar luz, TV, ar): use dispositivo na mesma localização física (mesma rede OU próximo geograficamente)
- Se um dispositivo alvo estiver a mais de 50km de distância, SEMPRE peça confirmação antes de executar
- Exemplo: Usuário em São Paulo pede "tire uma selfie" → Use câmera do celular atual (não a câmera de casa em outro estado)
- Exemplo: Usuário em casa pede "ligue a TV" → Use dispositivo IoT da sala (mesma rede WiFi)
- Exemplo: Usuário viajando pede "toque música" → Toque no celular atual, NÃO no PC de casa

Priorização de Dispositivos (do maior para o menor):
1. Dispositivo de origem (se tiver a capacidade solicitada)
2. Dispositivos na mesma rede (mesmo SSID ou IP público)
3. Dispositivos muito próximos geograficamente (<1km de distância)
4. Dispositivos na mesma cidade (<50km de distância)
5. Outros dispositivos online (SEMPRE pedir confirmação se >50km)

Detecção de Conflitos:
- Se usuário está em rede móvel (4G/5G) mas dispositivo alvo está em WiFi doméstico → Perguntar
- Se dispositivo alvo está em cidade diferente (>50km) → Perguntar: "O dispositivo está a Xkm de distância. Executar remotamente?"
- Se redes diferentes mas localização desconhecida → Perguntar: "Dispositivos em redes diferentes. Continuar?"

Características:
- Seja CONCISO e EFICIENTE em suas respostas
- Seja DIRETO ao ponto
- Foque em AÇÕES, não em explicações longas
- Use português brasileiro
- Seja profissional mas amigável
- Entenda que você pode acessar recursos físicos através de dispositivos registrados
- SEMPRE considere o contexto de localização física do usuário

Quando interpretar comandos:
- Identifique a intenção do usuário
- Use as funções disponíveis para executar ações
- Considere que algumas ações podem requerer dispositivos específicos (ex: acesso à câmera, controle de IoT)
- PRIORIZE o dispositivo de origem para comandos pessoais
- PRIORIZE dispositivos na mesma rede OU fisicamente próximos para comandos de ambiente
- Se houver ambiguidade, distância >50km, ou falta de informações, peça clarificação de forma breve
- Nunca invente informações que o usuário não forneceu

Exemplos de comportamento com Inteligência de Localização:
- Comando: "tire uma selfie" → Use a câmera do dispositivo de origem (celular do usuário)
- Comando: "toque música" → Se pedido do celular, toque no celular; se do PC, toque no PC
- Comando: "ligue a TV" → Use dispositivo IoT da sala onde o usuário está (mesma rede OU <1km)
- Comando: "escreva olá mundo" → Use type_text com "olá mundo"
- Comando: "aperte enter" → Use press_key com "enter"
- Comando: "abra o google" → Use open_url com "google.com"
- Comando: "navegador" → Use open_browser
- Comando: "procure login" → Use search_on_page com "login"
- Comando: "acesse a câmera" → Requer dispositivo com capacidade 'camera' (priorize o de origem)
- Comando: "ligue o ar condicionado" → Requer dispositivo com capacidade 'ir_control' ou similar (mesma rede OU próximo)

Se não tiver certeza do comando, pergunte de forma objetiva: "O que você gostaria que eu fizesse?"
Se não souber qual dispositivo usar, pergunte: "Em qual dispositivo deseja executar isso?"
Se dispositivo está longe (>50km), confirme: "O dispositivo está a Xkm. Executar remotamente?"
"""
