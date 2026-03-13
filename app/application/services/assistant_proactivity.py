# -*- coding: utf-8 -*-
"""AssistantService — Módulo de Proatividade.

Responsável por:
- Obter sugestões proativas do ProactiveCore
- Verificar intervalo entre sugestões (15 min)
- Filtrar sugestões por prioridade
"""
import logging
from datetime import datetime
from typing import Optional, Any

from app.core.nexus import nexus, CloudMock

logger = logging.getLogger(__name__)

# Intervalo entre verificações proativas
_PROACTIVITY_CHECK_INTERVAL_MINUTES = 15


def maybe_get_proactive_suggestion(
    user_id: Optional[str],
    last_proactive_check: datetime,
    command_history: list,
    proactive_core: Optional[Any] = None,
) -> tuple[Optional[str], datetime]:
    """
    Obtém sugestões proativas do ProactiveCore (se disponível).
    
    Verifica a cada 15 minutos para não ser intrusivo.
    
    Args:
        user_id: Identificador do usuário
        last_proactive_check: Última verificação proativa
        command_history: Histórico recente de comandos
        proactive_core: Instância do ProactiveCore (opcional)
        
    Returns:
        Tuple (sugestão, novo_timestamp)
    """
    # Verifica a cada 15 minutos
    elapsed = (datetime.now() - last_proactive_check).total_seconds() / 60
    if elapsed < _PROACTIVITY_CHECK_INTERVAL_MINUTES:
        return None, last_proactive_check
    
    new_check_time = datetime.now()
    
    try:
        if proactive_core is None:
            proactive_core = nexus.resolve("proactive_core_v2")        
        if proactive_core and not getattr(proactive_core, "__is_cloud_mock__", False):
            result = proactive_core.execute({
                "user_id": user_id,
                "force": False,
                "recent_commands": [c["command"] for c in command_history[-10:]],
                "config_snapshot": _get_config_snapshot(),
            })
            
            suggestions = result.get("suggestions", [])
            if suggestions:
                # Retorna primeira sugestão de alta prioridade
                high_priority = [s for s in suggestions if s.get("priority") == "high"]
                if high_priority:
                    message = high_priority[0].get("message")
                    logger.info(f"💡 Sugestão proativa: {message[:100]}")
                    return message, new_check_time
        
    except Exception as e:
        logger.debug(f"Erro ao obter sugestão proativa: {e}")
    
    return None, new_check_time


def _get_config_snapshot() -> dict:
    """
    Captura snapshot da configuração atual.
    
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