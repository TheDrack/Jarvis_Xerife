# -*- coding: utf-8 -*-
from typing import Dict, Any, List, Optional, TypedDict
import logging

logger = logging.getLogger(__name__)

class AgentAction(TypedDict):
    """Estrutura base para ações do agente."""
    type: str
    description: str
    payload: Dict[str, Any]

class ActionRegistry:
    """
    Registo e validador de ações do JarvisDevAgent.
    Define o que o agente pode ou não fazer no sistema.
    """

    def __init__(self):
        self.allowed_types = ["surgical_edit", "shell_command", "read_file", "list_dir"]
        # Lista negra de comandos proibidos por segurança
        self.blacklisted_patterns = ["rm -rf /", "mkfs", "shutdown", "reboot", ":(){ :|:& };:"]

    def validate_action(self, action: Dict[str, Any]) -> bool:
        """Valida se a ação é permitida e está bem formatada."""
        action_type = action.get("type")
        
        if action_type not in self.allowed_types:
            logger.warning(f"[Actions] Tipo de ação não permitido: {action_type}")
            return False

        # CORREÇÃO: Validação de segurança para comandos de shell
        if action_type == "shell_command":
            command = action.get("payload", {}).get("command", "")
            if any(pattern in command for pattern in self.blacklisted_patterns):
                logger.error(f"[Actions] Comando bloqueado por segurança: {command}")
                return False
        
        return True

    def create_shell_action(self, command: str, description: str) -> Dict[str, Any]:
        """Cria uma estrutura de ação de shell corrigida."""
        # CORREÇÃO: Sintaxe de dicionário corrigida na linha 50
        return {
            "type": "shell_command",
            "description": description,
            "payload": {
                "command": command,
                "timeout": 30
            }
        }

    def create_edit_action(self, file_path: str, search: str, replace: str) -> Dict[str, Any]:
        """Cria uma estrutura de ação de edição cirúrgica."""
        return {
            "type": "surgical_edit",
            "description": f"Editando {file_path}",
            "payload": {
                "file": file_path,
                "search": search,
                "replace": replace
            }
        }

    def parse_llm_response(self, raw_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Converte a resposta do LLM numa lista de ações validadas."""
        actions = raw_response.get("actions", [])
        validated = [a for a in actions if self.validate_action(a)]
        
        logger.info(f"[Actions] {len(validated)} ações validadas da resposta do LLM.")
        return validated
