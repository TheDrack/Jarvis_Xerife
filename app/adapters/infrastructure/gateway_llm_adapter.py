# -*- coding: utf-8 -*-
"""Enhanced LLM Command Adapter with AI Gateway integration

This adapter extends the base LLM functionality with intelligent routing
between multiple LLM providers through the AI Gateway.
"""

import asyncio
import logging
import os
import time
from typing import Optional

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider
from app.adapters.infrastructure.gemini_adapter import LLMCommandAdapter
from app.adapters.infrastructure.github_adapter import GitHubAdapter
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
    
    # Default model for auto-fix recommendations
    # Update this when new models are released
    RECOMMENDED_GEMINI_MODEL = "gemini-2.0-flash-exp"
    
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
        
        # Initialize GitHub adapter for self-healing
        try:
            self.github_adapter = GitHubAdapter()
            logger.info("GitHub adapter initialized for self-healing")
        except Exception as e:
            logger.warning(f"Failed to initialize GitHub adapter: {e}. Self-healing disabled.")
            self.github_adapter = None
        
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
            logger.error(f"Error generating conversational response: {e}", exc_info=True)
            
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
    
    async def _handle_critical_error(self, error: Exception, user_input: str) -> None:
        """
        Handle critical errors by triggering self-healing mechanism.
        
        Detects specific critical errors (model decommissioned, test failures, etc.)
        and triggers the auto-fix workflow via GitHub Actions.
        
        Args:
            error: The exception that occurred
            user_input: The user input that caused the error
        """
        if not self.github_adapter:
            logger.info("GitHub adapter not available, skipping self-healing")
            return
        
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Check for critical error patterns
        is_critical = any([
            "model_decommissioned" in error_str,
            "model has been decommissioned" in error_str,
            "model not found" in error_str,
            "test fail" in error_str,
            "quota" in error_str and "exceeded" in error_str,
            "rate limit" in error_str and "groq" not in error_str,  # Groq rate limits are handled by gateway
            "authentication failed" in error_str,
            "api key" in error_str and "invalid" in error_str,
        ])
        
        if not is_critical:
            logger.debug(f"Error is not critical, skipping self-healing: {error_type}")
            return
        
        logger.warning(f"🔧 Critical error detected: {error_type} - {error}")
        
        try:
            # Formulate a correction plan using Gemini
            fix_plan = await self._formulate_correction_plan(error, user_input)
            
            if fix_plan:
                # Dispatch auto-fix via GitHub
                logger.info(f"Dispatching auto-fix for critical error: {error_type}")
                result = await self.github_adapter.dispatch_auto_fix(fix_plan)
                
                if result.get("success"):
                    logger.info(f"✅ Auto-fix dispatched successfully: {result.get('workflow_url')}")
                else:
                    logger.error(f"❌ Failed to dispatch auto-fix: {result.get('error')}")
            else:
                logger.warning("Could not formulate a correction plan")
        
        except Exception as heal_error:
            logger.error(f"Error in self-healing process: {heal_error}", exc_info=True)
    
    async def _formulate_correction_plan(
        self, 
        error: Exception, 
        user_input: str
    ) -> Optional[dict]:
        """
        Use Gemini to formulate a correction plan for the detected error.
        
        Args:
            error: The exception that occurred
            user_input: The user input that caused the error
        
        Returns:
            Dictionary with fix plan (issue_title, file_path, fix_code, test_command)
            or None if unable to formulate a plan
        """
        if not self.gemini_adapter:
            logger.warning("Gemini adapter not available for correction planning")
            return None
        
        try:
            # Build diagnostic message
            error_type = type(error).__name__
            error_msg = str(error)
            
            diagnostic_prompt = f"""
ERRO CRÍTICO DETECTADO EM PRODUÇÃO

Tipo de Erro: {error_type}
Mensagem: {error_msg}
Input do Usuário: {user_input}

Contexto: O Jarvis está rodando no Render e detectou este erro crítico.

TAREFA: Analise o erro e determine se é possível formular uma correção automática.

Para erros relacionados a:
1. Model decommissioned/deprecated: Sugerir atualização do modelo
2. API key invalid: Indicar necessidade de configuração manual
3. Rate limits permanentes: Sugerir mudança de provider
4. Test failures: Analisar causa e propor correção

Responda em formato estruturado:
- É possível auto-correção? (sim/não)
- Arquivo afetado: (caminho completo do arquivo)
- Título da issue: (descrição breve)
- Comando de teste: (comando pytest específico ou vazio)
- Descrição técnica: (explicação do problema e solução)

Se não for possível auto-correção, explique o motivo.
"""
            
            # Get response from Gemini
            messages = [
                {"role": "user", "content": diagnostic_prompt}
            ]
            
            result = await self.gateway.generate_completion(
                messages=messages,
                functions=None,
                multimodal=False,
            )
            
            response_text = self._extract_response_text(result)
            
            if not response_text:
                logger.warning("No response from Gemini for correction planning")
                return None
            
            logger.info(f"Gemini analysis: {response_text}")
            
            # Parse the response to extract auto-fix information
            # For now, we'll use a simple heuristic approach
            # In a production system, you'd want more sophisticated parsing
            
            if "não" in response_text.lower() and "possível" in response_text.lower():
                logger.info("Gemini determined auto-fix is not possible")
                return None
            
            # Extract file path and create a basic fix plan
            # This is a simplified version - in production, you'd parse the response more carefully
            fix_plan = self._parse_fix_plan_from_response(response_text, error)
            
            return fix_plan
        
        except Exception as e:
            logger.error(f"Error formulating correction plan: {e}", exc_info=True)
            return None
    
    def _parse_fix_plan_from_response(
        self, 
        response: str, 
        error: Exception
    ) -> Optional[dict]:
        """
        Parse Gemini's response to extract fix plan details.
        
        Args:
            response: Gemini's text response
            error: The original error
        
        Returns:
            Dictionary with fix plan or None
        """
        # This is a simplified parser - in production, you'd use more sophisticated NLP
        # or ask Gemini to return JSON
        
        error_str = str(error).lower()
        
        # Default plan structure
        plan = {
            "issue_title": f"Auto-fix: {type(error).__name__}",
            "file_path": "",
            "fix_code": "",
            "test_command": "pytest -W ignore::DeprecationWarning tests/"
        }
        
        # Detect model decommissioned errors
        if "model_decommissioned" in error_str or "model has been decommissioned" in error_str:
            plan["issue_title"] = "Fix model_decommissioned error"
            plan["file_path"] = "app/adapters/infrastructure/gemini_adapter.py"
            
            # Read current file to create a fix
            # Note: Assumes current working directory is the repository root
            # This is true for GitHub Actions runners and typical deployment scenarios
            file_path = os.path.join(os.getcwd(), plan["file_path"])
            try:
                with open(file_path, "r") as f:
                    current_code = f.read()
                
                # Simple fix: replace deprecated model name with word boundaries
                # This ensures we don't replace parts of other strings
                import re
                new_model = self.RECOMMENDED_GEMINI_MODEL
                fixed_code = re.sub(
                    r'\bmodel_name:\s*str\s*=\s*"gemini-flash-latest"',
                    f'model_name: str = "{new_model}"',
                    current_code
                )
                fixed_code = re.sub(
                    r'\bgemini_model:\s*str\s*=\s*"gemini-flash-latest"',
                    f'gemini_model: str = "{new_model}"',
                    fixed_code
                )
                
                plan["fix_code"] = fixed_code
                plan["test_command"] = "pytest tests/adapters/ -k gemini -v"
                
                return plan
            except Exception as e:
                logger.error(f"Error reading file for fix: {e}")
                return None
        
        # For other errors, we need more information from the response
        # This is where you'd implement more sophisticated parsing
        logger.info("Error type not yet supported for automatic fixing")
        return None
