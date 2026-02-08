# -*- coding: utf-8 -*-
"""Infrastructure adapters for external services"""

# Import SQLiteHistoryAdapter (always available with core dependencies)
from .sqlite_history_adapter import SQLiteHistoryAdapter

# Import DummyVoiceProvider (always available, no dependencies)
from .dummy_voice_provider import DummyVoiceProvider

# Optional imports that require additional dependencies
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

__all__ = ["SQLiteHistoryAdapter", "DummyVoiceProvider"]

# Add optional exports if available
if LLMCommandAdapter is not None:
    __all__.append("LLMCommandAdapter")
if AIGateway is not None:
    __all__.extend(["AIGateway", "LLMProvider"])
if GatewayLLMCommandAdapter is not None:
    __all__.append("GatewayLLMCommandAdapter")
if create_api_server is not None:
    __all__.append("create_api_server")
