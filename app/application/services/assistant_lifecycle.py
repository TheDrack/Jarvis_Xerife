# -*- coding: utf-8 -*-
"""AssistantService — Módulo de Ciclo de Vida.

Responsável por:
- Start/Stop do serviço
- Health check loop (async)
- Monitoramento de componentes críticos
- Notificação de degradação
"""
import asyncio
import logging
from typing import Optional, Any, List

from app.core.config import settings
from app.core.nexus import nexus, CloudMock

logger = logging.getLogger(__name__)

# Intervalo do health check (5 minutos)
_HEALTH_CHECK_INTERVAL = 300


async def health_check_loop(
    is_running: callable,
    get_notification_service: callable,
    is_component_available: callable,
    health_check_task: Optional[asyncio.Task] = None,
) -> None:
    """
    Monitora componentes críticos e emite alertas via Nexus.
    
    Args:
        is_running: Função que retorna se o serviço está rodando
        get_notification_service: Função que retorna o notification_service
        is_component_available: Função que verifica disponibilidade de componente
        health_check_task: Task atual (para cancelamento)
    """
    while is_running():
        try:
            await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
            
            critical_components = [
                "command_interpreter",
                "intent_processor",
                "curiosity_engine",
                "learning_loop",
                "procedural_memory",
            ]
            unavailable = [
                c for c in critical_components                 if not is_component_available(c)
            ]
            
            if unavailable:
                logger.warning(
                    f"⚠️ Componentes críticos em modo degradado: {unavailable}"
                )
                
                notifier = get_notification_service()
                if notifier and not getattr(notifier, "__is_cloud_mock__", False):
                    notifier.send_alert(
                        title="Degradação de Sistema",
                        message=f"Componentes essenciais indisponíveis: {', '.join(unavailable)}",
                        severity="warning"
                    )
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Erro no health check: {e}")


def start_service(
    wake_word: str,
    is_running: callable,
    set_running: callable,
    create_health_task: callable,
) -> None:
    """
    Inicia o serviço do assistente e monitoramento.
    
    Args:
        wake_word: Palavra de ativação
        is_running: Função que retorna estado atual
        set_running: Função para definir estado
        create_health_task: Função para criar task de health check
    """
    if is_running():
        return
    
    set_running(True)
    logger.info(f"🤖 {getattr(settings, 'assistant_name', 'Jarvis')} iniciado - Wake word: '{wake_word}'")
    
    try:
        loop = asyncio.get_running_loop()
        create_health_task(loop)
    except RuntimeError:
        logger.warning("Event loop não encontrado. Health check não foi iniciado.")

def stop_service(
    is_running: callable,
    set_running: callable,
    health_check_task: Optional[asyncio.Task] = None,
) -> None:
    """
    Para o serviço e limpa tasks.
    
    Args:
        is_running: Função que retorna estado atual
        set_running: Função para definir estado
        health_check_task: Task de health check para cancelar
    """
    if not is_running():
        return
    
    set_running(False)
    
    if health_check_task:
        health_check_task.cancel()
    
    logger.info("🛑 Assistente parado")