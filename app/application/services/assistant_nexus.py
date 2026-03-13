# -*- coding: utf-8 -*-
"""AssistantService — Módulo de Contrato Nexus.

Responsável por:
- Implementar execute() para chamadas via Nexus
- Implementar can_execute() para validação
- Properties públicas para compatibilidade
- Versão assíncrona para API
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List

from app.core.nexus import nexus
from app.domain.models import Response

logger = logging.getLogger(__name__)


def nexus_execute(
    process_command: callable,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Implementação do contrato NexusComponent para chamadas via Nexus.
    
    Args:
        process_command: Função que processa comandos
        context: Contexto de execução do Nexus
        
    Returns:
        Dict com resultado da execução
    """
    if not context or "command" not in context:
        return {"success": False, "error": "Missing 'command' in execution context"}
    
    resp = process_command(
        command=context["command"],
        channel=context.get("channel", "nexus_internal"),
        user_id=context.get("user_id"),
    )
    
    return {
        "success": resp.success,
        "message": resp.message,
        "error": resp.error,
        "data": getattr(resp, "data", {})
    }

def nexus_can_execute(context: Optional[Dict[str, Any]] = None) -> bool:
    """
    Valida se o comando pode ser processado pelo Nexus.
    
    Args:
        context: Contexto de execução do Nexus
        
    Returns:
        True se pode executar, False caso contrário
    """
    return bool(
        context and 
        "command" in context and 
        isinstance(context["command"], str)
    )


async def async_process_command(
    process_command: callable,
    command: str,
    channel: str = "api",
    user_id: Optional[str] = None,
) -> Response:
    """
    Versão assíncrona para processamento de comandos via API/Websockets.
    
    Executa o processamento pesado/síncrono em um thread pool 
    para não travar o event loop.
    
    Args:
        process_command: Função que processa comandos
        command: Comando do usuário
        channel: Canal de origem
        user_id: Identificador do usuário
        
    Returns:
        Response com resultado
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: process_command(command, channel, user_id)
    )


def get_command_history(
    command_history: List[Dict[str, Any]],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """    Retorna histórico recente de comandos.
    
    Args:
        command_history: Lista completa de histórico
        limit: Número máximo de itens a retornar
        
    Returns:
        Lista dos últimos N comandos
    """
    return command_history[-limit:] if command_history else []


def clear_command_history(command_history: List[Dict[str, Any]]) -> None:
    """
    Limpa o histórico de comandos.
    
    Args:
        command_history: Lista de histórico para limpar
    """
    command_history.clear()