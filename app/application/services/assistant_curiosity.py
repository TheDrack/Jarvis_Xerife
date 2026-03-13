# -*- coding: utf-8 -*-
"""AssistantService — Módulo de Curiosidade.

Responsável por:
- Injetar perguntas de curiosidade contextualmente
- Capturar respostas do usuário para gaps
- Gerenciar cooldown entre perguntas
- Detectar gaps de configuração/conhecimento
"""
import logging
import random
from datetime import datetime
from typing import Optional, Dict, Any

from app.core.nexus import nexus, CloudMock

logger = logging.getLogger(__name__)

# Configurações de curiosidade
_CURIOSITY_QUESTION_CHANCE = 0.1  # 10% de chance de perguntar
_CURIOSITY_COOLDOWN_MINUTES = 30


def maybe_inject_curiosity_question(
    user_id: Optional[str],
    command: str,
    response: str,
    last_curiosity_asked_at: Optional[datetime] = None,
    curiosity_engine: Optional[Any] = None,
) -> tuple[Optional[str], Optional[datetime]]:
    """
    Decide se deve fazer pergunta de curiosidade baseada no contexto.
    
    Só pergunta 10% das vezes para não ser intrusivo.
    Usa CuriosityEngine para detectar gaps relevantes.
    
    Args:
        user_id: Identificador do usuário
        command: Comando do usuário
        response: Resposta gerada
        last_curiosity_asked_at: Última vez que perguntou
        curiosity_engine: Instância do CuriosityEngine (opcional)
        
    Returns:
        Tuple (pergunta, novo_timestamp) ou (None, timestamp_atual)
    """
    # Só pergunta 10% das vezes para não ser intrusivo
    if random.random() > _CURIOSITY_QUESTION_CHANCE:
        return None, last_curiosity_asked_at
        # Verifica cooldown (não perguntar se já perguntou há menos de 30 min)
    if last_curiosity_asked_at:
        elapsed = (datetime.now() - last_curiosity_asked_at).total_seconds() / 60
        if elapsed < _CURIOSITY_COOLDOWN_MINUTES:
            return None, last_curiosity_asked_at
    
    try:
        if curiosity_engine is None:
            curiosity_engine = nexus.resolve("curiosity_engine")
        
        if curiosity_engine and not getattr(curiosity_engine, "__is_cloud_mock__", False):
            config_snapshot = _get_config_snapshot()
            
            result = curiosity_engine.execute({
                "action": "detect_gaps",
                "command": command,
                "user_id": user_id,
                "config_snapshot": config_snapshot,
                "success": True,
            })
            
            question = result.get("question_to_ask")
            if question:
                logger.info(f"🤔 Curiosidade injetada: {question[:100]}")
                return question, datetime.now()
        
    except Exception as e:
        logger.debug(f"Erro ao injetar curiosidade: {e}")
    
    return None, last_curiosity_asked_at


def capture_curiosity_answer(
    command: str,
    pending_need_id: Optional[str],
    curiosity_engine: Optional[Any] = None,
) -> tuple[bool, Optional[str]]:
    """
    Verifica se comando atual é resposta para pergunta de curiosidade pendente.
    
    Args:
        command: Comando do usuário (provavelmente resposta)
        pending_need_id: ID da necessidade pendente
        curiosity_engine: Instância do CuriosityEngine (opcional)
        
    Returns:
        Tuple (sucesso, novo_need_id) — novo_need_id é None se capturado
    """
    if not pending_need_id:
        return False, pending_need_id    
    try:
        if curiosity_engine is None:
            curiosity_engine = nexus.resolve("curiosity_engine")
        
        if curiosity_engine and not getattr(curiosity_engine, "__is_cloud_mock__", False):
            result = curiosity_engine.execute({
                "action": "store_answer",
                "need_id": pending_need_id,
                "user_answer": command,
            })
            
            if result.get("success"):
                logger.info(f"✅ Resposta de curiosidade capturada: need_id={pending_need_id}")
                return True, None
        
    except Exception as e:
        logger.debug(f"Falha ao capturar resposta: {e}")
    
    return False, None


def _get_config_snapshot() -> Dict[str, Any]:
    """
    Captura snapshot da configuração atual para análise.
    
    Returns:
        Dict com configuração do sistema
    """
    config = {
        "llm_providers": [],
        "voice_enabled": False,
        "calendar_connected": False,
        "interaction_count": 0,
        "preferences_set": False,
        "channel": "api",
    }
    
    # Verifica providers configurados
    try:
        gateway = nexus.resolve("ai_gateway")
        if gateway and not getattr(gateway, "__is_cloud_mock__", False):
            if hasattr(gateway, "gemini_key") and gateway.gemini_key:
                config["llm_providers"].append("gemini")
            if hasattr(gateway, "groq_key") and gateway.groq_key:
                config["llm_providers"].append("groq")
    except Exception:
        pass
    
    return config