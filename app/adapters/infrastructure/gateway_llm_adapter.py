# -*- coding: utf-8 -*-
"""Enhanced LLM Command Adapter with AI Gateway integration

This adapter extends the base LLM functionality with intelligent routing
between multiple LLM providers through the AI Gateway.
"""

import logging
from typing import Optional

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider
from app.adapters.infrastructure.gemini_adapter import LLMCommandAdapter
from app.application.ports import VoiceProvider
from app.domain.models import CommandType, Intent

logger = logging.getLogger(__name__)


class GatewayLLMCommandAdapter:
    """
    Enhanced LLM Command Adapter that uses AI Gateway for intelligent provider routing.
    
    Features:
    - Uses Groq by default for fast, cost-effective processing
    - Automatically escalates to Gemini for large payloads (>10k tokens)
    - Falls back to Gemini on Groq rate limits
    - Maintains backward compatibility with LLMCommandAdapter interface
    """
    
    # Default system instruction for conversational responses
    DEFAULT_SYSTEM_INSTRUCTION = (
        "Você é um assistente virtual amigável e prestativo. "
        "Responda de forma conversacional em português brasileiro."
    )
    
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        groq_model: str = "llama-3.3-70b-versatile",
        gemini_model: str = "gemini-flash-latest",
        voice_provider: Optional[VoiceProvider] = None,
        wake_word: str = "xerife",
        history_provider: Optional["HistoryProvider"] = None,
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
        """
        self.wake_word = wake_word
        self.voice_provider = voice_provider
        self.history_provider = history_provider
        
        # Initialize AI Gateway
        self.gateway = AIGateway(
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            groq_model=groq_model,
            gemini_model=gemini_model,
            default_provider=LLMProvider.GROQ,
        )
        
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
        
        logger.info("Gateway LLM Command Adapter initialized with AI Gateway")
    
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
        # For interpretation, we primarily use the Gemini adapter as it's
        # already well-integrated with the function calling system
        # The AI Gateway is more useful for general conversational responses
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
    
    def generate_conversational_response(self, user_input: str) -> str:
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
            
            # Add system instruction
            messages.append({
                "role": "system",
                "content": self.DEFAULT_SYSTEM_INSTRUCTION
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
            
            # Generate response using AI Gateway
            result = self.gateway.generate_completion(
                messages=messages,
                functions=None,  # No function calling for conversational response
                multimodal=False,
            )
            
            logger.info(f"Response generated by: {result['provider']}")
            
            # Extract text from response based on provider
            response_text = self._extract_response_text(result)
            
            return response_text if response_text else "Desculpe, não entendi. Pode repetir?"
            
        except Exception as e:
            logger.error(f"Error generating conversational response: {e}", exc_info=True)
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
