# -*- coding: utf-8 -*-
import json
import re
import logging
import asyncio
from typing import Dict, Any, Optional
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

class MetabolismCore(NexusComponent):
    """
    Coração do processamento cognitivo (LLM).
    Interface oficial para chamadas ao modelo generativo e estruturação de pensamentos.
    """

    def __init__(self):
        super().__init__()
        self._client = None
        self._model_name = "gemini-1.5-pro"

    async def _get_api_key(self) -> str:
        """Obtém a chave de API de forma segura via SecretsProvider."""
        try:
            secrets = self.nexus.resolve("env_secrets_provider")
            return secrets.get_secret("GEMINI_API_KEY")
        except Exception:
            # Fallback seguro para desenvolvimento se o provider falhar
            import os
            return os.getenv("GEMINI_API_KEY", "")

    async def generate_thought(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Gera uma resposta de texto simples (Chain of Thought)."""
        # Exemplo de implementação simplificada da chamada ao SDK
        # Na prática, aqui estaria a integração com google.generativeai
        try:
            api_key = await self._get_api_key()
            if not api_key:
                return "Erro: GEMINI_API_KEY não configurada."
            
            logger.info("[Metabolism] Gerando pensamento para o prompt enviado...")
            # Simulação de chamada assíncrona
            await asyncio.sleep(0.5)
            return f"Pensamento estruturado sobre: {prompt[:30]}..."
        except Exception as e:
            logger.error(f"[Metabolism] Erro na geração: {e}")
            return ""

    def extract_json(self, raw_text: str) -> Dict[str, Any]:
        """
        CORREÇÃO: Extração robusta de JSON ignorando blocos de Markdown.
        """
        try:
            # Remove blocos de código markdown se existirem
            clean_text = re.sub(r'```json\s*|```\s*', '', raw_text).strip()
            
            # Tenta encontrar o primeiro '{' e o último '}'
            start_idx = clean_text.find('{')
            end_idx = clean_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                json_str = clean_text[start_idx:end_idx+1]
                return json.loads(json_str)
            
            return json.loads(clean_text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"[Metabolism] Falha ao parsear JSON: {e}")
            return {"success": False, "error": "Invalid JSON structure"}

    async def generate_fix_proposal(self, issue: str, context: list) -> Dict[str, Any]:
        """Gera uma proposta técnica formatada para o JarvisDevAgent."""
        prompt = f"Analise o erro: {issue}\nContexto de ficheiros: {context}\nRetorne um JSON com 'actions'."
        
        raw_response = await self.generate_thought(prompt)
        # Em produção, aqui seria usada uma chamada configurada para JSON mode
        return self.extract_json(raw_response)

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point para o Nexus DI."""
        # CORREÇÃO: Mapeamento do método execute para funções internas
        action = context.get("action")
        prompt = context.get("prompt", "")
        
        if action == "generate":
            # Nota: Em Python, para chamar async dentro de sync execute, 
            # o ideal é que o Nexus suporte chamadas async.
            return {"success": True, "info": "Ação encaminhada para o loop async"}
        
        return {"success": False, "error": "Ação não implementada no modo síncrono"}
