# -*- coding: utf-8 -*-
"""
LLM Configuration for Command Interpretation and Capability Detection

This module provides configuration for switching between keyword-based
and LLM-based identification systems.
"""

import logging
import os

logger = logging.getLogger(__name__)


class LLMConfig:
    """Configuration for LLM-based identification features"""

    @classmethod
    def use_llm_command_interpretation(cls) -> bool:
        """Returns whether LLM-based command interpretation is enabled."""
        return os.getenv("JARVIS_USE_LLM_COMMANDS", "true").lower() == "true"

    @classmethod
    def use_llm_capability_detection(cls) -> bool:
        """Returns whether LLM-based capability detection is enabled."""
        return os.getenv("JARVIS_USE_LLM_CAPABILITIES", "true").lower() == "true"

    @classmethod
    def use_copilot_context(cls) -> bool:
        """Returns whether GitHub Copilot context generation is enabled."""
        return os.getenv("JARVIS_USE_COPILOT_CONTEXT", "true").lower() == "true"

    @classmethod
    def command_llm_provider(cls) -> str:
        """Returns the LLM provider for command interpretation."""
        return os.getenv("JARVIS_COMMAND_LLM_PROVIDER", "auto")

    @classmethod
    def capability_llm_provider(cls) -> str:
        """Returns the LLM provider for capability detection."""
        return os.getenv("JARVIS_CAPABILITY_LLM_PROVIDER", "auto")

    @classmethod
    def min_command_confidence(cls) -> float:
        """Returns the minimum confidence threshold for command interpretation."""
        return float(os.getenv("JARVIS_MIN_COMMAND_CONFIDENCE", "0.6"))

    @classmethod
    def min_capability_confidence(cls) -> float:
        """Returns the minimum confidence threshold for capability detection."""
        return float(os.getenv("JARVIS_MIN_CAPABILITY_CONFIDENCE", "0.7"))

    @classmethod
    def max_capabilities_per_scan(cls) -> int:
        """Returns the maximum number of capabilities per scan batch."""
        return int(os.getenv("JARVIS_MAX_CAPABILITIES_PER_SCAN", "10"))

    # ---------------------------------------------------------------------------
    # Backward-compatible class-level aliases (read at import time)
    # ---------------------------------------------------------------------------
    USE_LLM_COMMAND_INTERPRETATION: bool = os.getenv("JARVIS_USE_LLM_COMMANDS", "true").lower() == "true"
    USE_LLM_CAPABILITY_DETECTION: bool = os.getenv("JARVIS_USE_LLM_CAPABILITIES", "true").lower() == "true"
    USE_COPILOT_CONTEXT: bool = os.getenv("JARVIS_USE_COPILOT_CONTEXT", "true").lower() == "true"
    COMMAND_LLM_PROVIDER: str = os.getenv("JARVIS_COMMAND_LLM_PROVIDER", "auto")
    CAPABILITY_LLM_PROVIDER: str = os.getenv("JARVIS_CAPABILITY_LLM_PROVIDER", "auto")
    MIN_COMMAND_CONFIDENCE: float = float(os.getenv("JARVIS_MIN_COMMAND_CONFIDENCE", "0.6"))
    MIN_CAPABILITY_CONFIDENCE: float = float(os.getenv("JARVIS_MIN_CAPABILITY_CONFIDENCE", "0.7"))
    MAX_CAPABILITIES_PER_SCAN: int = int(os.getenv("JARVIS_MAX_CAPABILITIES_PER_SCAN", "10"))

    @classmethod
    def get_config_summary(cls) -> dict:
        """Get a summary of current LLM configuration"""
        return {
            "llm_command_interpretation": cls.use_llm_command_interpretation(),
            "llm_capability_detection": cls.use_llm_capability_detection(),
            "copilot_context_generation": cls.use_copilot_context(),
            "command_llm_provider": cls.command_llm_provider(),
            "capability_llm_provider": cls.capability_llm_provider(),
            "min_command_confidence": cls.min_command_confidence(),
            "min_capability_confidence": cls.min_capability_confidence(),
        }

    @classmethod
    def validate_config(cls) -> bool:
        """
        Validate configuration and log warnings for potential issues

        Returns:
            True if configuration is valid, False otherwise
        """
        valid = True

        # Check confidence thresholds
        if not (0.0 <= cls.min_command_confidence() <= 1.0):
            logger.error(
                f"Invalid MIN_COMMAND_CONFIDENCE: {cls.min_command_confidence()}. "
                "Must be between 0.0 and 1.0"
            )
            valid = False

        if not (0.0 <= cls.min_capability_confidence() <= 1.0):
            logger.error(
                f"Invalid MIN_CAPABILITY_CONFIDENCE: {cls.min_capability_confidence()}. "
                "Must be between 0.0 and 1.0"
            )
            valid = False

        # Check provider values
        valid_providers = ["groq", "gemini", "auto"]
        if cls.command_llm_provider() not in valid_providers:
            logger.warning(
                f"Invalid COMMAND_LLM_PROVIDER: {cls.command_llm_provider()}. "
                f"Valid options: {valid_providers}. Using 'auto'."
            )

        if cls.capability_llm_provider() not in valid_providers:
            logger.warning(
                f"Invalid CAPABILITY_LLM_PROVIDER: {cls.capability_llm_provider()}. "
                f"Valid options: {valid_providers}. Using 'auto'."
            )

        # Warn if all LLM features are disabled
        if not any([
            cls.use_llm_command_interpretation(),
            cls.use_llm_capability_detection(),
            cls.use_copilot_context()
        ]):
            logger.warning(
                "All LLM features are disabled. Using traditional keyword-based systems."
            )

        return valid


def create_command_interpreter(wake_word: str = "xerife", ai_gateway=None):
    """
    Factory function to create the appropriate command interpreter

    Args:
        wake_word: Wake word for the interpreter
        ai_gateway: Optional AI Gateway instance

    Returns:
        Either LLMCommandInterpreter or CommandInterpreter based on configuration
    """
    # Check if LLM is enabled AND ai_gateway is provided
    if LLMConfig.use_llm_command_interpretation() and ai_gateway is not None:
        from app.domain.services.llm_command_interpreter import LLMCommandInterpreter
        logger.info("Creating LLM-based command interpreter")
        return LLMCommandInterpreter(wake_word=wake_word, ai_gateway=ai_gateway)
    else:
        from app.domain.services.command_interpreter import CommandInterpreter
        logger.info("Creating keyword-based command interpreter (LLM disabled or unavailable)")
        return CommandInterpreter(wake_word=wake_word)


def create_capability_manager(engine, ai_gateway=None):
    """
    Factory function to create the appropriate capability manager

    Args:
        engine: SQLAlchemy engine
        ai_gateway: Optional AI Gateway instance

    Returns:
        Either EnhancedCapabilityManager or CapabilityManager based on configuration
    """
    from app.application.services.capability_manager import CapabilityManager

    base_manager = CapabilityManager(engine)

    if LLMConfig.use_llm_capability_detection() and ai_gateway:
        from app.application.services.llm_capability_detector import EnhancedCapabilityManager
        logger.info("Creating LLM-enhanced capability manager")
        return EnhancedCapabilityManager(base_manager=base_manager, ai_gateway=ai_gateway)
    else:
        logger.info("Creating standard capability manager (LLM disabled or unavailable)")
        return base_manager


def create_copilot_context_provider(repository_root=None, ai_gateway=None):
    """
    Factory function to create GitHub Copilot context provider

    Args:
        repository_root: Root directory of the repository
        ai_gateway: Optional AI Gateway instance

    Returns:
        GitHubCopilotContextProvider instance or None if disabled
    """
    if LLMConfig.use_copilot_context() and ai_gateway:
        from app.adapters.infrastructure.copilot_context_provider import GitHubCopilotContextProvider
        logger.info("Creating GitHub Copilot context provider")
        return GitHubCopilotContextProvider(
            ai_gateway=ai_gateway,
            repository_root=repository_root
        )
    else:
        logger.info("GitHub Copilot context provider disabled")
        return None


# Initialize configuration validation on module load
_config_valid = LLMConfig.validate_config()
if _config_valid:
    logger.info("LLM configuration validated successfully")
    logger.debug(f"LLM config: {LLMConfig.get_config_summary()}")

# Nexus Compatibility
LlmConfig = LLMConfig
