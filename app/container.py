# -*- coding: utf-8 -*-
"""Dependency Injection Container - Wires together all components"""

import logging
import os
import sys
from typing import Optional

from app.adapters.edge import AutomationAdapter, CombinedVoiceProvider, WebAdapter
from app.adapters.infrastructure import DummyVoiceProvider, LLMCommandAdapter, SQLiteHistoryAdapter
from app.application.ports import ActionProvider, HistoryProvider, VoiceProvider, WebProvider
from app.application.services import AssistantService, DependencyManager, ExtensionManager
from app.core.config import settings
from app.domain.services import CommandInterpreter, IntentProcessor

logger = logging.getLogger(__name__)


def _is_headless_environment() -> bool:
    """
    Detect if we're running in a headless environment (tests, CI/CD, cloud).
    
    Returns:
        True if running in headless environment, False otherwise
    """
    # Check if running in pytest
    if "pytest" in sys.modules:
        return True
    
    # Check if running in CI/CD (common CI environment variables)
    ci_vars = ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "TRAVIS", "CIRCLECI"]
    if any(os.getenv(var) for var in ci_vars):
        return True
    
    # Check if running on cloud platform (Render, Heroku, etc.)
    # Render sets both PORT and RENDER environment variables
    # Heroku sets both PORT and DYNO environment variables
    if os.getenv("PORT") and (os.getenv("RENDER") or os.getenv("DYNO") or os.getenv("RENDER_SERVICE_NAME")):
        return True
    
    return False


class Container:
    """
    Dependency Injection Container for the application.
    Manages creation and lifecycle of all components.
    """

    def __init__(
        self,
        voice_provider: Optional[VoiceProvider] = None,
        action_provider: Optional[ActionProvider] = None,
        web_provider: Optional[WebProvider] = None,
        history_provider: Optional[HistoryProvider] = None,
        wake_word: str = "xerife",
        language: str = "pt-BR",
        use_llm: bool = False,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-1.5-flash",
        db_path: str = "jarvis.db",
    ):
        """
        Initialize the container

        Args:
            voice_provider: Optional pre-configured voice provider
            action_provider: Optional pre-configured action provider
            web_provider: Optional pre-configured web provider
            history_provider: Optional pre-configured history provider
            wake_word: Wake word for the assistant
            language: Language for voice recognition
            use_llm: Whether to use LLM-based command interpretation (default: False)
            gemini_api_key: Optional Gemini API key (defaults to GEMINI_API_KEY env var)
            gemini_model: Gemini model name to use (default: gemini-1.5-flash)
            db_path: Path to SQLite database file (default: jarvis.db)
        """
        self.wake_word = wake_word
        self.language = language
        self.use_llm = use_llm
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_model = gemini_model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.db_path = db_path

        # Create or use provided adapters
        self._voice_provider = voice_provider
        self._action_provider = action_provider
        self._web_provider = web_provider
        self._history_provider = history_provider

        # Domain services (always created fresh)
        self._command_interpreter: Optional[CommandInterpreter] = None
        self._llm_command_adapter: Optional[LLMCommandAdapter] = None
        self._intent_processor: Optional[IntentProcessor] = None
        self._dependency_manager: Optional[DependencyManager] = None
        self._extension_manager: Optional[ExtensionManager] = None

        # Application service
        self._assistant_service: Optional[AssistantService] = None

    @property
    def voice_provider(self) -> VoiceProvider:
        """Get or create voice provider"""
        if self._voice_provider is None:
            # Use DummyVoiceProvider in headless environments
            if _is_headless_environment():
                logger.info("Detected headless environment, using DummyVoiceProvider")
                self._voice_provider = DummyVoiceProvider()
            else:
                logger.info("Creating default CombinedVoiceProvider")
                self._voice_provider = CombinedVoiceProvider(
                    language=self.language,
                    ambient_noise_adjustment=True,
                )
        return self._voice_provider

    @property
    def action_provider(self) -> ActionProvider:
        """Get or create action provider"""
        if self._action_provider is None:
            logger.info("Creating default AutomationAdapter")
            self._action_provider = AutomationAdapter(
                pause=0.4,
                search_timeout=7.5,
            )
        return self._action_provider

    @property
    def web_provider(self) -> WebProvider:
        """Get or create web provider"""
        if self._web_provider is None:
            logger.info("Creating default WebAdapter")
            self._web_provider = WebAdapter(self.action_provider)
        return self._web_provider

    @property
    def history_provider(self) -> HistoryProvider:
        """Get or create history provider"""
        if self._history_provider is None:
            logger.info(f"Creating SQLiteHistoryAdapter with database configuration")
            # Use DATABASE_URL from settings if it's not the default SQLite
            # Only use SQLite fallback (db_path) if the URL is the exact default
            database_url = None
            if settings.database_url and settings.database_url != "sqlite:///jarvis.db":
                # Custom database URL (could be PostgreSQL, another SQLite path, etc.)
                database_url = settings.database_url
            
            self._history_provider = SQLiteHistoryAdapter(
                db_path=self.db_path,
                database_url=database_url
            )
        return self._history_provider

    @property
    def command_interpreter(self) -> CommandInterpreter:
        """Get or create command interpreter"""
        if self._command_interpreter is None:
            if self.use_llm:
                # Use LLM-based adapter
                logger.info("Using LLMCommandAdapter for command interpretation")
                if self._llm_command_adapter is None:
                    self._llm_command_adapter = LLMCommandAdapter(
                        api_key=self.gemini_api_key,
                        model_name=self.gemini_model,
                        voice_provider=self.voice_provider,
                        wake_word=self.wake_word,
                        history_provider=self.history_provider,
                    )
                return self._llm_command_adapter
            else:
                # Use rule-based interpreter
                logger.info("Using rule-based CommandInterpreter")
                self._command_interpreter = CommandInterpreter(wake_word=self.wake_word)
        return self._command_interpreter

    @property
    def intent_processor(self) -> IntentProcessor:
        """Get or create intent processor"""
        if self._intent_processor is None:
            self._intent_processor = IntentProcessor()
        return self._intent_processor

    @property
    def dependency_manager(self) -> DependencyManager:
        """Get or create dependency manager"""
        if self._dependency_manager is None:
            logger.info("Creating DependencyManager")
            self._dependency_manager = DependencyManager()
        return self._dependency_manager

    @property
    def extension_manager(self) -> ExtensionManager:
        """Get or create extension manager"""
        if self._extension_manager is None:
            logger.info("Creating ExtensionManager")
            self._extension_manager = ExtensionManager()
        return self._extension_manager

    @property
    def assistant_service(self) -> AssistantService:
        """Get or create assistant service with all dependencies injected"""
        if self._assistant_service is None:
            logger.info("Creating AssistantService with injected dependencies")
            self._assistant_service = AssistantService(
                voice_provider=self.voice_provider,
                action_provider=self.action_provider,
                web_provider=self.web_provider,
                command_interpreter=self.command_interpreter,
                intent_processor=self.intent_processor,
                history_provider=self.history_provider,
                dependency_manager=self.dependency_manager,
                wake_word=self.wake_word,
            )
        return self._assistant_service


def create_edge_container(
    wake_word: str = "xerife",
    language: str = "pt-BR",
    use_llm: bool = False,
) -> Container:
    """
    Factory function to create a container with edge adapters

    Args:
        wake_word: Wake word for the assistant
        language: Language for voice recognition
        use_llm: Whether to use LLM-based command interpretation (default: False)

    Returns:
        Configured container with edge adapters
    """
    return Container(wake_word=wake_word, language=language, use_llm=use_llm)
