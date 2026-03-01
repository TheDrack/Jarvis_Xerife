# -*- coding: utf-8 -*-
"""Infrastructure adapters for external services"""

# Import DummyVoiceProvider (sempre disponível, sem dependências)
from .dummy_voice_provider import DummyVoiceProvider

# Importação Protegida do SQLiteHistoryAdapter (Evita erro se SQLAlchemy não existir)
try:
    from .sqlite_history_adapter import SQLiteHistoryAdapter
except ImportError:
    SQLiteHistoryAdapter = None

# Optional imports
try:
    from .gemini_adapter import LLMCommandAdapter
except ImportError:
    LLMCommandAdapter = None

try:
    from .ai_gateway import AIGateway, LLMProvider
except ImportError:
    AIGateway = None
    LLMProvider = None

try:
    from .gateway_llm_adapter import GatewayLLMCommandAdapter
except ImportError:
    GatewayLLMCommandAdapter = None

try:
    from .api_server import create_api_server
except ImportError:
    create_api_server = None

# Lista de exportação dinâmica
__all__ = ["DummyVoiceProvider"]

if SQLiteHistoryAdapter is not None:
    __all__.append("SQLiteHistoryAdapter")
if LLMCommandAdapter is not None:
    __all__.append("LLMCommandAdapter")
if AIGateway is not None:
    __all__.extend(["AIGateway", "LLMProvider"])
if GatewayLLMCommandAdapter is not None:
    __all__.append("GatewayLLMCommandAdapter")
if create_api_server is not None:
    __all__.append("create_api_server")
