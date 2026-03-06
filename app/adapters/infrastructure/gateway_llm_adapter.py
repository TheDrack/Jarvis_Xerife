from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Enhanced LLM Command Adapter with AI Gateway integration

This adapter extends the base LLM functionality with intelligent routing
between multiple LLM providers through the AI Gateway.
"""

import asyncio
import functools
import logging
import os
import time
import traceback
from typing import Optional

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider
from app.adapters.infrastructure.auto_repair_mixin import AutoRepairMixin
from app.adapters.infrastructure.gemini_adapter import LLMCommandAdapter
from app.adapters.infrastructure.github_adapter import GitHubAdapter
from app.application.ports import VoiceProvider
from app.domain.models import CommandType, Intent
from app.domain.services.agent_service import AgentService
from app.domain.services.llm_command_interpreter import LLMCommandInterpreter

logger = logging.getLogger(__name__)


class GatewayLLMCommandAdapter(AutoRepairMixin):
    """
    Enhanced LLM Command Adapter that uses AI Gateway for intelligent provider routing.

    Features:
    - Uses Groq by default for fast, cost-effective processing
    - Automatically escalates to Gemini for large payloads (>10k tokens)
    - Falls back to Gemini on Groq rate limits
    - Maintains backward compatibility with LLMCommandAdapter interface
    """
    
    # System instruction for conversational responses - uses Xerife personality from AgentService
    # Using functools.lru_cache for thread-safe initialization
    # Note: The cache is intentionally global (staticmethod) because the system instruction
    # is configuration-based and does not change during runtime. This provides better
    # performance by sharing the same instruction across all instances.
    @staticmethod
    @functools.lru_cache(maxsize=1)
    def get_system_instruction() -> str:
        """Get the system instruction (thread-safe, cached globally)."""
        return AgentService.get_system_instruction()
    
    # Default model for auto-fix recommendations
    # Update this when new models are released
    RECOMMENDED_GEMINI_MODEL = "gemini-2.0-flash"
    
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        groq_model: str = "llama-3.3-70b-versatile",
        gemini_model: str = "gemini-flash-latest",
        voice_provider: Optional[VoiceProvider] = None,
        wake_word: str = "xerife",
        history_provider: Optional["HistoryProvider"] = None,
        use_llm: bool = True,
    ):
        """
        Initialize the Gateway LLM Command Adapter.
        
        Args:
            groq_api_key: Groq API key (defaults to GROQ_API_KEY env var)
            gemini_api_key: Gemini API key (defaults to GOOGLE_API_KEY env var)
            groq_model: Groq model name
            gemini_model: Gemini model name
            voice_provider: Optional voice provider for clarifications
            wake_word: The wake word to filter out from commands
            history_provider: Optional history provider for context
            use_llm: Whether to use LLM for error analysis and auto-repair (default: True)
        """
        self.wake_word = wake_word
        self.voice_provider = voice_provider
        self.history_provider = history_provider
        self.use_llm = use_llm
        
        # Track errors locally to prevent infinite loops
        self._error_log_file = "/tmp/jarvis_auto_repair_errors.log"
        
        # Initialize AI Gateway
        self.gateway = AIGateway(
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            groq_model=groq_model,
            gemini_model=gemini_model,
            default_provider=LLMProvider.GROQ,
        )

        self.llm_interpreter = None
        try:
            from app.core.llm_config import LLMConfig
            if LLMConfig.use_llm_command_interpretation():
                self.llm_interpreter = LLMCommandInterpreter(
                    wake_word=wake_word,
                    ai_gateway=self.gateway,
                )
                logger.info("LLMCommandInterpreter initialized for command interpretation")
        except Exception as e:
            logger.warning(f"Failed to initialize LLMCommandInterpreter: {e}")
        
        # Also initialize a fallback Gemini adapter for certain operations
        # that need Gemini-specific features
        try:
            self.gemini_adapter = LLMCommandAdapter(
                api_key=gemini_api_key,
                model_name=gemini_model,
                voice_provider=voice_provider,
                wake_word=wake_word,
                history_provider=history_provider,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini fallback adapter: {e}")
            self.gemini_adapter = None
        
        # Initialize GitHub adapter for self-healing
        try:
            self.github_adapter = GitHubAdapter()
            logger.info("GitHub adapter initialized for self-healing")
        except Exception as e:
            logger.warning(f"Failed to initialize GitHub adapter: {e}. Self-healing disabled.")
            self.github_adapter = None
        
        logger.info("Gateway LLM Command Adapter initialized with AI Gateway")

    def execute(self, context: dict) -> dict:
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    def _interpret_sync(self, raw_input: str) -> Intent:
        """Synchronous interpretation calling the Gemini client directly.

        Avoids calling ``self.interpret()`` to prevent infinite recursion when
        an asyncio event loop is already active.  Mirrors the logic of
        ``interpret_async`` but executes synchronously via the underlying
        Gemini adapter's ``_interpret_sync``, bypassing any asyncio machinery.

        Args:
            raw_input: Raw text from voice or text input.

        Returns:
            Intent object with command type and parameters.
        """
        # Delegate to gemini_adapter._interpret_sync which calls the Gemini
        # client directly without going through asyncio.to_thread.
        if self.gemini_adapter is not None:
            sync_fn = getattr(self.gemini_adapter, "_interpret_sync", None)
            if sync_fn is not None:
                return sync_fn(raw_input)

        # Fallback: return unknown intent when no synchronous path is available.
        command = raw_input.lower().strip()
        if self.wake_word in command:
            command = command.replace(self.wake_word, "").strip()
        logger.warning("[GatewayLLM] _interpret_sync: no synchronous Gemini client available")
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": command},
            raw_input=raw_input,
            confidence=0.0,
        )

    def interpret(self, raw_input: str) -> Intent:
        """
        Interpret a raw text command into a structured Intent.
        
        Uses AI Gateway to automatically select the best provider based on
        payload size and availability.
        
        Args:
            raw_input: Raw text from voice or text input
            
        Returns:
            Intent object with command type and parameters
        """
        if self.llm_interpreter:
            return self.llm_interpreter.interpret(raw_input)
        
        # Fallback to Gemini adapter for interpretation if available
        if self.gemini_adapter:
            return self.gemini_adapter.interpret(raw_input)
        
        # Fallback: return unknown intent
        logger.warning("No adapter available for interpretation")
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": raw_input},
            raw_input=raw_input,
            confidence=0.0,
        )

    async def interpret_async(self, raw_input: str) -> Intent:
        """
        Async interpretation of a raw text command into a structured Intent.
        
        Args:
            raw_input: Raw text from voice or text input
            
        Returns:
            Intent object with command type and parameters
        """
        if self.llm_interpreter:
            return await self.llm_interpreter.interpret_async(raw_input)
        
        if self.gemini_adapter:
            interpret_async = getattr(self.gemini_adapter, "interpret_async", None)
            if interpret_async and asyncio.iscoroutinefunction(interpret_async):
                return await interpret_async(raw_input)
            return await asyncio.to_thread(self.gemini_adapter.interpret, raw_input)
        
        logger.warning("No adapter available for async interpretation")
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": raw_input},
            raw_input=raw_input,
            confidence=0.0,
        )
    
    def is_exit_command(self, raw_input: str) -> bool:
        """
        Check if the input is an exit command.
        
        Args:
            raw_input: Raw text input
            
        Returns:
            True if it's an exit command
        """
        exit_keywords = ["fechar", "sair", "encerrar", "tchau"]
        command = raw_input.lower().strip()
        return any(keyword in command for keyword in exit_keywords)
    
    def is_cancel_command(self, raw_input: str) -> bool:
        """
        Check if the input is a cancel command.
        
        Args:
            raw_input: Raw text input
            
        Returns:
            True if it's a cancel command
        """
        cancel_keywords = ["cancelar", "parar", "stop"]
        command = raw_input.lower().strip()
        return any(keyword in command for keyword in cancel_keywords)
    
    async def generate_conversational_response(self, user_input: str) -> str:
        """
        Generate a conversational response using AI Gateway.
        
        This method intelligently routes to Groq for short responses and
        Gemini for longer contexts, with automatic fallback on rate limits.
        
        Args:
            user_input: User's input text
            
        Returns:
            Generated conversational response
        """
        try:
            # Start timing for latency measurement
            start_time = time.time()
            
            # Normalize input
            command = user_input.lower().strip()
            
            # Remove wake word if present
            if self.wake_word in command:
                command = command.replace(self.wake_word, "").strip()
            
            if not command:
                return "Olá! Como posso ajudar?"
            
            # Build context from history if available
            context_message = self._build_context_message()
            
            # Prepare messages for AI Gateway
            messages = []
            
            # Add system instruction - use Xerife personality from AgentService
            messages.append({
                "role": "system",
                "content": self.get_system_instruction()
            })
            
            # Add context if available
            if context_message:
                messages.append({
                    "role": "system",
                    "content": context_message
                })
            
            # Add user message
            messages.append({
                "role": "user",
                "content": command
            })
            
            # Generate response using AI Gateway with await
            result = await self.gateway.generate_completion(
                messages=messages,
                functions=None,  # No function calling for conversational response
                multimodal=False,
            )
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            logger.info(f"Response generated by: {result['provider']} in {latency_ms:.2f}ms")
            
            # Extract text from response based on provider
            response_text = self._extract_response_text(result)
            
            return response_text if response_text else "Desculpe, não entendi. Pode repetir?"
            
        except Exception as e:
            # Capture full error traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Error generating conversational response: {e}")
            logger.error(f"Full traceback:\n{error_traceback}")
            
            # Log error locally to prevent infinite loop
            self._log_error_locally(error_traceback)
            
            # If use_llm is enabled, attempt auto-repair
            if self.use_llm:
                try:
                    await self._attempt_auto_repair(error_traceback, user_input)
                except Exception as repair_error:
                    logger.error(f"Error during auto-repair attempt: {repair_error}", exc_info=True)
                    # Log this too to prevent loops
                    self._log_error_locally(f"Auto-repair failed: {traceback.format_exc()}")
            
            # Check if this is a critical error that requires self-healing
            await self._handle_critical_error(e, user_input)
            
            return "Desculpe, ocorreu um erro. Pode tentar novamente?"
    
    def _extract_response_text(self, result: dict) -> Optional[str]:
        """
        Extract response text from AI Gateway result.
        
        Args:
            result: Result dict from AI Gateway
            
        Returns:
            Extracted text or None
        """
        provider = result.get("provider")
        response = result.get("response")
        
        if provider == LLMProvider.GROQ.value:
            # Groq returns OpenAI-compatible format
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    return choice.message.content
        
        elif provider == LLMProvider.GEMINI.value:
            # Gemini format
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            return part.text.strip()
        
        return None
    
    def _build_context_message(self) -> str:
        """
        Build context message from the last 3 commands in history.
        
        Returns:
            Formatted context string or empty string if no history
        """
        if not self.history_provider:
            return ""
        
        try:
            # Get last 3 commands from history
            recent_history = self.history_provider.get_recent_history(limit=3)
            if not recent_history:
                return ""
            
            # Build context message
            context_lines = ["Contexto (últimos comandos executados):"]
            for item in reversed(recent_history):  # Show oldest first
                command_type = item.get("command_type", "unknown")
                user_input = item.get("user_input", "")
                success = item.get("success", False)
                status = "sucesso" if success else "falhou"
                context_lines.append(f"- '{user_input}' -> {command_type} ({status})")
            
            return "\n".join(context_lines)
        except Exception as e:
            logger.warning(f"Error building context message: {e}")
            return ""
    
    def _log_error_locally(self, error_message: str) -> None:
        """
        Log error locally to prevent infinite loop of repair attempts.
        
        Args:
            error_message: The error message to log
        """
        try:
            with open(self._error_log_file, "a") as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {error_message}\n")
                f.write("-" * 80 + "\n")
            logger.info(f"Error logged locally to {self._error_log_file}")
        except Exception as e:
            logger.error(f"Failed to log error locally: {e}")

# Nexus Compatibility
GatewayLlmAdapter = GatewayLLMCommandAdapter
