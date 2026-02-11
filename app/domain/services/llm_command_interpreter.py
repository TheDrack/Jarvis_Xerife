# -*- coding: utf-8 -*-
"""LLM-based Command Interpreter - Uses AI to identify commands with higher accuracy

This interpreter replaces keyword-based pattern matching with LLM-based understanding,
providing more accurate and flexible command interpretation.
"""

import asyncio
import logging
from typing import Optional
from app.domain.models import CommandType, Intent
from app.adapters.infrastructure.ai_gateway import LLMProvider
from app.core.llm_config import LLMConfig

logger = logging.getLogger(__name__)


class LLMCommandInterpreter:
    """
    Interprets raw text commands into structured Intents using LLM.
    Uses AI Gateway (Groq/Gemini) to understand user intent with higher accuracy
    than keyword matching.
    """

    def __init__(self, wake_word: str = "xerife", ai_gateway=None):
        """
        Initialize the LLM command interpreter

        Args:
            wake_word: The wake word to filter out from commands
            ai_gateway: AI Gateway instance for LLM integration
        """
        self.wake_word = wake_word
        self.ai_gateway = ai_gateway
        
        # Always initialize fallback interpreter for reliability
        from app.domain.services.command_interpreter import CommandInterpreter
        self._fallback_interpreter = CommandInterpreter(wake_word=wake_word)
        self._min_confidence = LLMConfig.MIN_COMMAND_CONFIDENCE
        self._forced_provider = self._resolve_provider(LLMConfig.COMMAND_LLM_PROVIDER)
        
        if not self.ai_gateway:
            logger.warning("No AI Gateway provided, will use keyword-based fallback")

    async def interpret_async(self, raw_input: str) -> Intent:
        """
        Interpret a raw text command into a structured Intent using LLM
        
        Args:
            raw_input: Raw text from voice or text input
            
        Returns:
            Intent object with command type and parameters
        """
        # Normalize input
        command = raw_input.lower().strip()

        # Remove wake word if present
        if self.wake_word in command:
            command = command.replace(self.wake_word, "").strip()
            raw_input_lower = raw_input.lower()
            wake_pos = raw_input_lower.find(self.wake_word)
            if wake_pos != -1:
                raw_input = raw_input[wake_pos + len(self.wake_word):].strip()

        # Use AI Gateway for intent classification if available
        if self.ai_gateway:
            try:
                return await self._llm_interpret(raw_input, command)
            except Exception as e:
                logger.error(f"LLM interpretation failed: {e}. Using fallback.", exc_info=True)
        
        # Fallback to keyword-based interpretation
        if self._fallback_interpreter:
            return self._fallback_interpreter.interpret(raw_input)
        
        # Ultimate fallback: return UNKNOWN
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": command},
            raw_input=raw_input,
            confidence=0.5,
        )

    def interpret(self, raw_input: str) -> Intent:
        """
        Synchronous version that uses fallback interpreter
        
        For async LLM interpretation, use interpret_async()
        
        Args:
            raw_input: Raw text from voice or text input
            
        Returns:
            Intent object with command type and parameters
        """
        if self.ai_gateway:
            try:
                asyncio.get_running_loop()
                logger.warning("Event loop already running, using keyword fallback for sync interpret")
                return self._fallback_interpretation(raw_input)
            except RuntimeError:
                try:
                    return asyncio.run(self.interpret_async(raw_input))
                except Exception as e:
                    logger.error(f"Sync LLM interpretation failed: {e}. Using fallback.", exc_info=True)
                    return self._fallback_interpretation(raw_input)
        
        if self._fallback_interpreter:
            return self._fallback_interpreter.interpret(raw_input)
        
        # If no fallback, return UNKNOWN
        command = raw_input.lower().strip()
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": command},
            raw_input=raw_input,
            confidence=0.5,
        )

    async def _llm_interpret(self, raw_input: str, normalized_command: str) -> Intent:
        """
        Use LLM to interpret command with high accuracy
        
        Args:
            raw_input: Original raw input
            normalized_command: Normalized command text
            
        Returns:
            Intent object classified by LLM
        """
        # Build prompt for LLM to classify command
        classification_prompt = self._build_classification_prompt(normalized_command)
        
        messages = [
            {"role": "system", "content": self._get_system_instruction()},
            {"role": "user", "content": classification_prompt}
        ]
        
        # Get LLM response
        result = await self.ai_gateway.generate_completion(
            messages=messages,
            functions=None,
            multimodal=False,
            force_provider=self._forced_provider,
        )
        
        # Parse response to extract intent
        response_text = self._extract_response_text(result)
        if not response_text:
            logger.warning("Empty response from LLM, using fallback")
            return self._fallback_interpretation(raw_input)
        
        # Parse LLM response into Intent
        return self._parse_llm_response(response_text, raw_input, normalized_command)

    def _build_classification_prompt(self, command: str) -> str:
        """Build classification prompt for LLM"""
        return f"""Classifique o seguinte comando e extraia os parâmetros:

Comando: "{command}"

Tipos de comando disponíveis:
- TYPE_TEXT: digitar texto (ex: "escreva olá", "digite meu nome")
- PRESS_KEY: pressionar tecla (ex: "aperte enter", "pressione F5")
- OPEN_BROWSER: abrir navegador (ex: "internet", "abrir navegador")
- OPEN_URL: abrir site (ex: "site google.com", "abrir youtube")
- SEARCH_ON_PAGE: buscar na página (ex: "procurar login", "clicar em botão")
- REPORT_ISSUE: reportar problema (ex: "reportar bug", "criar issue")
- UNKNOWN: comando não reconhecido

Responda APENAS em formato JSON:
{{
  "command_type": "TIPO_DO_COMANDO",
  "parameters": {{"chave": "valor"}},
  "confidence": 0.0-1.0,
  "reasoning": "breve explicação"
}}

Exemplos de parâmetros:
- TYPE_TEXT: {{"text": "texto a digitar"}}
- PRESS_KEY: {{"key": "nome da tecla"}}
- OPEN_URL: {{"url": "url completa"}}
- SEARCH_ON_PAGE: {{"search_text": "texto a buscar"}}
- REPORT_ISSUE: {{"issue_description": "descrição", "context": "contexto"}}
"""

    def _get_system_instruction(self) -> str:
        """Get system instruction for LLM classification"""
        return """Você é um classificador de comandos de voz inteligente para o Jarvis.
Sua tarefa é identificar a intenção do usuário e extrair os parâmetros relevantes.
Seja preciso e confiante. Se não tiver certeza, use confidence < 0.7."""

    def _extract_response_text(self, result: dict) -> Optional[str]:
        """Extract response text from AI Gateway result"""
        provider = result.get("provider")
        response = result.get("response")
        
        if provider == "groq":
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    return choice.message.content
        
        elif provider == "gemini":
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            return part.text.strip()
        
        return None

    def _parse_llm_response(
        self, 
        response_text: str, 
        raw_input: str, 
        normalized_command: str
    ) -> Intent:
        """Parse LLM JSON response into Intent"""
        import json
        
        try:
            # Clean up response to extract JSON
            json_text = response_text.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()
            
            data = json.loads(json_text)
            
            # Map string command type to enum
            command_type_raw = data.get("command_type", "UNKNOWN")
            if not isinstance(command_type_raw, str):
                logger.warning(
                    "Command type from LLM must be a string, got "
                    f"{type(command_type_raw).__name__}"
                )
                return self._fallback_interpretation(raw_input)
            
            command_type_str = command_type_raw.upper()
            try:
                command_type = CommandType[command_type_str]
            except KeyError:
                logger.warning(f"Unknown command type from LLM: {command_type_str}")
                command_type = CommandType.UNKNOWN
            
            parameters = data.get("parameters", {})
            confidence = float(data.get("confidence", 0.7))
            
            if confidence < self._min_confidence:
                logger.warning(
                    f"LLM confidence {confidence:.2f} below minimum "
                    f"{self._min_confidence:.2f}. Using fallback."
                )
                return self._fallback_interpretation(raw_input)
            
            logger.info(f"LLM classified as {command_type} with {confidence:.2f} confidence")
            logger.debug(f"LLM reasoning: {data.get('reasoning', 'N/A')}")
            
            return Intent(
                command_type=command_type,
                parameters=parameters,
                raw_input=raw_input,
                confidence=confidence,
            )
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response was: {response_text}")
            return self._fallback_interpretation(raw_input)

    def _fallback_interpretation(self, raw_input: str) -> Intent:
        """Fallback when LLM fails"""
        if self._fallback_interpreter:
            return self._fallback_interpreter.interpret(raw_input)
        
        # Ultimate fallback: return UNKNOWN
        normalized_command = raw_input.lower().strip()
        return Intent(
            command_type=CommandType.UNKNOWN,
            parameters={"raw_command": normalized_command},
            raw_input=raw_input,
            confidence=0.3,
        )

    def _resolve_provider(self, provider_setting: str) -> Optional[LLMProvider]:
        """Resolve provider based on configuration"""
        provider_setting = provider_setting.lower()
        if provider_setting == "groq":
            return LLMProvider.GROQ
        if provider_setting == "gemini":
            return LLMProvider.GEMINI
        return None

    def is_exit_command(self, raw_input: str) -> bool:
        """
        Check if the input is an exit command
        
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
        Check if the input is a cancel command
        
        Args:
            raw_input: Raw text input
            
        Returns:
            True if it's a cancel command
        """
        cancel_keywords = ["cancelar", "parar", "stop"]
        command = raw_input.lower().strip()
        return any(keyword in command for keyword in cancel_keywords)
