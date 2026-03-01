# -*- coding: utf-8 -*-
"""
Infrastructure adapters for external services.
Implementação de Lazy Loading para máxima eficiência e isolamento de dependências.
"""

import importlib
from typing import Any

# Mapeamento de componentes para seus respectivos módulos
_COMPONENT_MAP = {
    "DummyVoiceProvider": ".dummy_voice_provider",
    "SQLiteHistoryAdapter": ".sqlite_history_adapter",
    "LLMCommandAdapter": ".gemini_adapter",
    "AIGateway": ".ai_gateway",
    "LLMProvider": ".ai_gateway",
    "GatewayLLMCommandAdapter": ".gateway_llm_adapter",
    "create_api_server": ".api_server"
}

def __getattr__(name: str) -> Any:
    """
    Realiza a importação dinâmica apenas quando o atributo é acessado.
    Isso evita erros de MRO e dependências ausentes durante a inicialização global.
    """
    if name in _COMPONENT_MAP:
        module_path = _COMPONENT_MAP[name]
        try:
            # Importa o módulo de forma relativa
            module = importlib.import_module(module_path, __package__)
            return getattr(module, name)
        except (ImportError, TypeError, AttributeError) as e:
            # Se a dependência falhar (ex: SQLAlchemy) ou houver erro de MRO, 
            # retorna None em vez de quebrar o sistema inteiro.
            import logging
            logging.warning(f"⚠️ [INFRA] Falha ao carregar '{name}' via Lazy Load: {e}")
            return None

    raise AttributeError(f"module {__name__} has no attribute {name}")

# Define o que é visível (embora o __getattr__ cuide da lógica)
__all__ = list(_COMPONENT_MAP.keys())
