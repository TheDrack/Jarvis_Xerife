# -*- coding: utf-8 -*-
"""AssistantService - Serviço central de processamento de comandos."""
import logging
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class CommandResult:
    """Resultado de execução de comando."""
    def __init__(self, success: bool = False, message: str = "", error: Optional[str] = None):
        self.success = success
        self.message = message
        self.error = error


class AssistantService(NexusComponent):
    """Serviço principal de assistência - processa comandos via múltiplos canais."""

    def __init__(self):
        super().__init__()
        self.interpreter = None
        self.intent_processor = None
        logger.info("🤖 [ASSISTANT] Inicializado")

    def configure(self, config: Dict[str, Any]) -> None:
        """Configuração opcional via NexusComponent."""
        pass

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre pronto para processar comandos."""
        return True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent - delega para process_command."""
        ctx = context or {}
        cmd = ctx.get("command", "")
        channel = ctx.get("channel", "api")
        user_id = ctx.get("user_id", "default")

        result = self.process_command(cmd, channel, user_id)
        return {
            "success": result.success,
            "message": result.message,
            "error": result.error,
        }

    def process_command(self, command: str, channel: str = "api", user_id: str = "default_user") -> CommandResult:
        """Processa um comando do usuário via um canal específico.

        Args:
            command: Comando ou mensagem do usuário
            channel: Canal de entrada ("api", "telegram", "voice", etc)
            user_id: ID do usuário

        Returns:
            CommandResult com sucesso, mensagem e erro (se houver)
        """
        try:
            if not command or not isinstance(command, str):
                return CommandResult(
                    success=False,
                    message="Comando vazio ou inválido",
                    error="EMPTY_COMMAND"
                )

            logger.info(f"📨 [ASSISTANT] Recebido comando via {channel}: {command[:50]}...")

            # Rota básica: echo para validação funcional
            # Em produção, seria interpretado e processado
            response_text = f"Comando processado: {command}"

            return CommandResult(
                success=True,
                message=response_text,
                error=None
            )

        except Exception as e:
            logger.error(f"❌ [ASSISTANT] Erro ao processar comando: {e}", exc_info=True)
            return CommandResult(
                success=False,
                message="Erro ao processar comando",
                error=str(e)
            )
