# -*- coding: utf-8 -*-
"""AssistantService — Módulo de Aprendizado (RL/ML).

Responsável por:
- Verificar soluções internas antes de LLM externo
- Registrar interações para aprendizado futuro
- Inferir tipo de tarefa baseado no comando
- Detectar qual LLM foi usado
"""
import logging
from typing import Optional, Any, Dict
from app.core.nexus import nexus, CloudMock

logger = logging.getLogger(__name__)

# Threshold de confiança para usar solução interna
_INTERNAL_SOLUTION_CONFIDENCE_THRESHOLD = 0.75


def check_internal_solution(
    command: str,
    task_type: str,
    learning_loop: Optional[Any] = None,
    procedural_memory: Optional[Any] = None,
) -> Optional[str]:
    """
    Verifica se existe solução interna antes de chamar LLM externo.
    
    Args:
        command: Comando do usuário
        task_type: Tipo de tarefa inferido
        learning_loop: Instância do LearningLoop (opcional)
        procedural_memory: Instância do ProceduralMemory (opcional)
        
    Returns:
        Solução interna se encontrada, None caso contrário
    """
    try:
        # Lazy loading se não fornecido
        if learning_loop is None:
            learning_loop = nexus.resolve("learning_loop")
        if procedural_memory is None:
            procedural_memory = nexus.resolve("procedural_memory")
        
        # Tenta via LearningLoop primeiro
        if learning_loop and not getattr(learning_loop, "__is_cloud_mock__", False):
            result = learning_loop.execute({
                "action": "check_internal",
                "command": command,
                "task_type": task_type,                "min_confidence": _INTERNAL_SOLUTION_CONFIDENCE_THRESHOLD,
            })
            
            if result.get("use_internal") and result.get("solution"):
                logger.info(
                    f"✅ Solução INTERNA via LearningLoop: "
                    f"{result.get('pattern_id')} (confiança: {result.get('confidence', 0):.2f})"
                )
                return result["solution"]
        
        # Fallback: busca direta em ProceduralMemory
        if procedural_memory and not getattr(procedural_memory, "__is_cloud_mock__", False):
            result = procedural_memory.execute({
                "action": "find_similar",
                "command": command,
                "task_type": task_type,
                "min_confidence": _INTERNAL_SOLUTION_CONFIDENCE_THRESHOLD,
            })
            
            if result.get("found") and result.get("can_use_internally"):
                logger.info(
                    f"✅ Padrão encontrado em ProceduralMemory: "
                    f"{result.get('pattern_id')} (confiança: {result.get('confidence', 0):.2f})"
                )
                return result.get("solution")
        
    except Exception as e:
        logger.debug(f"Erro ao verificar solução interna: {e}")
    
    return None


def record_learning_interaction(
    command: str,
    response: str,
    llm_used: str,
    success: bool,
    reward: float,
    task_type: str,
    user_id: Optional[str] = None,
    learning_loop: Optional[Any] = None,
) -> None:
    """
    Registra interação com LLM para aprendizado futuro.
    
    Cada interação com LLM externo é um investimento para não precisar dele no futuro.
    
    Args:
        command: Comando do usuário
        response: Resposta gerada        llm_used: Qual LLM foi usado (gemini, groq, ollama, internal, etc.)
        success: Se a interação foi bem sucedida
        reward: Reward signal para RL
        task_type: Tipo de tarefa
        user_id: Identificador do usuário
        learning_loop: Instância do LearningLoop (opcional)
    """
    try:
        if learning_loop is None:
            learning_loop = nexus.resolve("learning_loop")
        
        if learning_loop and not getattr(learning_loop, "__is_cloud_mock__", False):
            learning_loop.execute({
                "action": "record_episode",
                "command": command,
                "task_type": task_type,
                "llm_response": response,
                "llm_used": llm_used,
                "success": success,
                "reward": reward,
                "metadata": {
                    "user_id": user_id,
                }
            })
            
    except Exception as e:
        logger.debug(f"Erro ao registrar interação: {e}")


def infer_task_type(command: str) -> str:
    """
    Infer tipo de tarefa baseado no comando.
    
    Usado para categorizar aprendizado e buscar padrões similares.
    
    Args:
        command: Comando do usuário
        
    Returns:
        Tipo de tarefa (code_generation, scheduling, voice, etc.)
    """
    command_lower = command.lower()
    
    if any(w in command_lower for w in ["código", "python", "gere", "crie", "função", "script"]):
        return "code_generation"
    elif any(w in command_lower for w in ["analise", "debug", "erro", "bug", "corrija"]):
        return "code_analysis"
    elif any(w in command_lower for w in ["lembrete", "agenda", "calendário", "compromisso"]):
        return "scheduling"
    elif any(w in command_lower for w in ["voz", "áudio", "fale", "ouça", "grave"]):        return "voice"
    elif any(w in command_lower for w in ["status", "sistema", "health", "diagnóstico"]):
        return "system_query"
    elif any(w in command_lower for w in ["arquivo", "pasta", "diretório", "salve"]):
        return "file_operation"
    elif any(w in command_lower for w in ["busque", "pesquise", "encontre"]):
        return "search"
    else:
        return "general_conversation"


def detect_llm_used(result_data: Any) -> str:
    """
    Detecta qual LLM foi usado baseado nos metadados da resposta.
    
    Args:
        result_data: Dados de resultado do processamento
        
    Returns:
        Nome do LLM usado (gemini, groq, ollama, internal, unknown)
    """
    if isinstance(result_data, dict):
        return result_data.get("provider", result_data.get("llm_used", "unknown"))
    return "unknown"


def extract_result_message(result_data: Any) -> str:
    """
    Extrai mensagem de resposta do resultado.
    
    Args:
        result_data: Dados de resultado do processamento
        
    Returns:
        Mensagem de resposta como string
    """
    if isinstance(result_data, dict):
        return result_data.get("message", str(result_data))
    return str(result_data)