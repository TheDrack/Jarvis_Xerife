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
    
    # Enable/disable LLM-based command interpretation
    # When False, uses traditional keyword-based interpretation
    USE_LLM_COMMAND_INTERPRETATION = os.getenv(
        "JARVIS_USE_LLM_COMMANDS", 
        "true"
    ).lower() == "true"
    
    # Enable/disable LLM-based capability detection
    # When False, uses traditional keyword-based detection
    USE_LLM_CAPABILITY_DETECTION = os.getenv(
        "JARVIS_USE_LLM_CAPABILITIES",
        "true"
    ).lower() == "true"
    
    # Enable/disable GitHub Copilot context generation
    # When False, does not generate repository context for GitHub Agents
    USE_COPILOT_CONTEXT = os.getenv(
        "JARVIS_USE_COPILOT_CONTEXT",
        "true"
    ).lower() == "true"
    
    # LLM provider preference for command interpretation
    # Options: "groq", "gemini", "auto" (auto uses AI Gateway's logic)
    COMMAND_LLM_PROVIDER = os.getenv(
        "JARVIS_COMMAND_LLM_PROVIDER",
        "auto"
    )
    
    # LLM provider preference for capability detection
    # Options: "groq", "gemini", "auto"
    CAPABILITY_LLM_PROVIDER = os.getenv(
        "JARVIS_CAPABILITY_LLM_PROVIDER",
        "auto"
    )
    
    # Minimum confidence threshold for LLM-based command interpretation
    # Commands with confidence below this threshold will use fallback
    MIN_COMMAND_CONFIDENCE = float(os.getenv(
        "JARVIS_MIN_COMMAND_CONFIDENCE",
        "0.6"
    ))
    
    # Minimum confidence threshold for LLM-based capability detection
    # Capability status updates with confidence below this threshold are ignored
    MIN_CAPABILITY_CONFIDENCE = float(os.getenv(
        "JARVIS_MIN_CAPABILITY_CONFIDENCE",
        "0.7"
    ))
    
    # Maximum number of capabilities to scan in a single batch
    # This helps manage LLM API costs and processing time
    MAX_CAPABILITIES_PER_SCAN = int(os.getenv(
        "JARVIS_MAX_CAPABILITIES_PER_SCAN",
        "10"
    ))
    
    @classmethod
    def get_config_summary(cls) -> dict:
        """Get a summary of current LLM configuration"""
        return {
            "llm_command_interpretation": cls.USE_LLM_COMMAND_INTERPRETATION,
            "llm_capability_detection": cls.USE_LLM_CAPABILITY_DETECTION,
            "copilot_context_generation": cls.USE_COPILOT_CONTEXT,
            "command_llm_provider": cls.COMMAND_LLM_PROVIDER,
            "capability_llm_provider": cls.CAPABILITY_LLM_PROVIDER,
            "min_command_confidence": cls.MIN_COMMAND_CONFIDENCE,
            "min_capability_confidence": cls.MIN_CAPABILITY_CONFIDENCE,
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
        if not (0.0 <= cls.MIN_COMMAND_CONFIDENCE <= 1.0):
            logger.error(
                f"Invalid MIN_COMMAND_CONFIDENCE: {cls.MIN_COMMAND_CONFIDENCE}. "
                "Must be between 0.0 and 1.0"
            )
            valid = False
        
        if not (0.0 <= cls.MIN_CAPABILITY_CONFIDENCE <= 1.0):
            logger.error(
                f"Invalid MIN_CAPABILITY_CONFIDENCE: {cls.MIN_CAPABILITY_CONFIDENCE}. "
                "Must be between 0.0 and 1.0"
            )
            valid = False
        
        # Check provider values
        valid_providers = ["groq", "gemini", "auto"]
        if cls.COMMAND_LLM_PROVIDER not in valid_providers:
            logger.warning(
                f"Invalid COMMAND_LLM_PROVIDER: {cls.COMMAND_LLM_PROVIDER}. "
                f"Valid options: {valid_providers}. Using 'auto'."
            )
        
        if cls.CAPABILITY_LLM_PROVIDER not in valid_providers:
            logger.warning(
                f"Invalid CAPABILITY_LLM_PROVIDER: {cls.CAPABILITY_LLM_PROVIDER}. "
                f"Valid options: {valid_providers}. Using 'auto'."
            )
        
        # Warn if all LLM features are disabled
        if not any([
            cls.USE_LLM_COMMAND_INTERPRETATION,
            cls.USE_LLM_CAPABILITY_DETECTION,
            cls.USE_COPILOT_CONTEXT
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
    if LLMConfig.USE_LLM_COMMAND_INTERPRETATION and ai_gateway is not None:
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
    
    if LLMConfig.USE_LLM_CAPABILITY_DETECTION and ai_gateway:
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
    if LLMConfig.USE_COPILOT_CONTEXT and ai_gateway:
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
