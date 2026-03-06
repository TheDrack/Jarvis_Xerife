from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""AI Gateway Token Utilities - Token counting helpers."""

import logging
from typing import Any, Dict, Optional

# Try to import tiktoken, but don't fail if it's not available
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    tiktoken = None
    HAS_TIKTOKEN = False

logger = logging.getLogger(__name__)

# Module-level tokenizer cache to avoid repeated initialization
_TOKENIZER_CACHE = None


def _get_tokenizer():
    """Get or create tokenizer with caching"""
    global _TOKENIZER_CACHE
    if not HAS_TIKTOKEN:
        return None

    if _TOKENIZER_CACHE is None:
        try:
            # Using cl100k_base encoding (GPT-4, GPT-3.5-turbo)
            # This is a good approximation for most modern LLMs
            _TOKENIZER_CACHE = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to initialize tokenizer: {e}. Token counting will be approximate.")
            _TOKENIZER_CACHE = False  # Use False to indicate initialization was attempted but failed
    return _TOKENIZER_CACHE if _TOKENIZER_CACHE else None


def count_tokens(text: str) -> int:
    """
    Count tokens in the given text.

    Uses tiktoken if available, otherwise falls back to character-based approximation
    using a 1:4 ratio (1 token ≈ 4 characters).

    Args:
        text: Text to count tokens for

    Returns:
        Approximate token count
    """
    if HAS_TIKTOKEN:
        tokenizer = _get_tokenizer()
        if tokenizer:
            try:
                return len(tokenizer.encode(text))
            except Exception as e:
                logger.warning(f"Error counting tokens: {e}. Using character approximation.")

    # Fallback: rough approximation (1 token ≈ 4 characters)
    return len(text) // 4


class TokenCounter(NexusComponent):
    """NexusComponent wrapper for token counting functionality."""

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Count tokens for the text provided in context.

        Args:
            context: Dict with optional key ``text`` (str). If absent, returns 0.

        Returns:
            Evidence dict with ``token_count`` and ``success``.
        """
        text = (context or {}).get("text", "")
        token_count = count_tokens(text)
        return {
            "success": True,
            "token_count": token_count,
            "text_length": len(text),
        }
