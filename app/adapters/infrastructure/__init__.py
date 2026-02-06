# -*- coding: utf-8 -*-
"""Infrastructure adapters for external services"""

# Import SQLiteHistoryAdapter (always available with core dependencies)
from .sqlite_history_adapter import SQLiteHistoryAdapter

# Optional imports that require additional dependencies
try:
    from .gemini_adapter import LLMCommandAdapter
except ImportError:
    LLMCommandAdapter = None

try:
    from .api_server import create_api_server
except ImportError:
    create_api_server = None

__all__ = ["SQLiteHistoryAdapter"]

# Add optional exports if available
if LLMCommandAdapter is not None:
    __all__.append("LLMCommandAdapter")
if create_api_server is not None:
    __all__.append("create_api_server")
