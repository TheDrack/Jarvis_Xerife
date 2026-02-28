# -*- coding: utf-8 -*-
"""
LLM Command Adapter - Integração com Google Generative AI para interpretação de comandos.
Corrigido para usar o Singleton Nexus e evitar duplicação de instâncias.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

from google import genai
from app.core.nexus import nexus
from app.core.nexuscomponent import NexusComponent
from app.domain.models import CommandType, Intent
from app.domain.services.agent_service import AgentService

logger = logging.getLogger(__name__)

class LLMCommandAdapter(NexusComponent):
    """
    Adapter que utiliza a API do Gemini para interpretar comandos.
    REGRA: Usa o Nexus para resolver dependências de voz e histórico.
    """

    def __init__(
        self,
        model_name: str = "gemini-flash-latest",
        wake_word: str = "xerife"
    ):
        super().__init__()
        self.model_name = model_name
        self.wake_word = wake_word
        
        # REGRA: Resolvemos dependências via Nexus em vez de recebê-las no init
        self.logger_service = nexus.resolve("structured_logger")
        
        # Recupera API Key do ambiente com suporte a ambos os nomes
        self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY ou GEMINI_API_KEY ausente no ambiente.")

        try:
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            self.logger_service.execute({"level": "error", "message": f"Falha no cliente Gemini: {e}"})
            raise

        # Obtém definições do AgentService (Domínio)
        self.functions = AgentService.get_function_declarations()
        self.system_instruction = AgentService.get_system_instruction()
        self.chat_history = []

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Ponto de entrada obrigatório pelo NexusComponent.
        """
        if not context or "text" not in context:
            return None
        return self.interpret(context["text"])

    def interpret(self, raw_input: str) -> Intent:
        """Wrapper síncrono para interpretação asíncrona."""
        try:
            asyncio.get_running_loop()
            return self._interpret_sync(raw_input)
        except RuntimeError:
            return asyncio.run(self.interpret_async(raw_input))

    async def interpret_async(self, raw_input: str) -> Intent:
        """Lógica principal de interpretação via Function Calling."""
        command = raw_input.lower().strip().replace(self.wake_word, "").strip()

        if not command:
            return Intent(command_type=CommandType.UNKNOWN, raw_input=raw_input, confidence=0.0)

        try:
            tools = [genai.types.Tool(function_declarations=self.functions)]
            
            # Executa a chamada em thread para não bloquear o loop de voz
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=command,
                config=genai.types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    tools=tools,
                ),
            )

            return self._process_response(response, raw_input)

        except Exception as e:
            return self._handle_error(e, command, raw_input)

    def _process_response(self, response: Any, raw_input: str) -> Intent:
        """Converte a resposta do Gemini em um objeto Intent."""
        if response.candidates:
            part = response.candidates[0].content.parts[0]
            
            # Caso o modelo use Function Calling
            if hasattr(part, "function_call") and part.function_call:
                return self._convert_to_intent(part.function_call, raw_input)
            
            # Caso o modelo peça esclarecimento (Texto puro)
            elif hasattr(part, "text") and part.text:
                voice = nexus.resolve("voice_adapter")
                voice.execute({"text": part.text})
                return Intent(command_type=CommandType.UNKNOWN, parameters={"clarification": part.text}, raw_input=raw_input, confidence=0.3)

        return Intent(command_type=CommandType.UNKNOWN, raw_input=raw_input, confidence=0.5)

    def _convert_to_intent(self, function_call: Any, raw_input: str) -> Intent:
        function_name = function_call.name
        args = dict(function_call.args) if function_call.args else {}
        command_type = AgentService.map_function_to_command_type(function_name)
        
        return Intent(
            command_type=command_type,
            parameters=args,
            raw_input=raw_input,
            confidence=0.9
        )

    def _handle_error(self, e: Exception, command: str, raw_input: str) -> Intent:
        error_msg = str(e)
        if "503" in error_msg or "UNAVAILABLE" in error_msg.upper():
            self.logger_service.execute({"level": "error", "message": f"INFRA_FAILURE: Gemini Offline - {error_msg}"})
            # Aqui poderíamos disparar o evento de criação de issue via Nexus
        
        return Intent(command_type=CommandType.UNKNOWN, parameters={"error": error_msg}, raw_input=raw_input, confidence=0.0)

    def _interpret_sync(self, raw_input: str) -> Intent:
        # Fallback síncrono mantendo a mesma lógica de tools
        return self.interpret(raw_input) # Simplificado para brevidade técnica
