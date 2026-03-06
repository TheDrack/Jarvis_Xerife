# -*- coding: utf-8 -*-
"""OllamaAdapter — LLMs locais via Ollama.

Implementa a mesma interface do GeminiAdapter e GroqAdapter.
Conecta-se ao endpoint local do Ollama (padrão: http://localhost:11434).
Configurável via variável de ambiente OLLAMA_BASE_URL.
"""
import json
import logging
import os
import urllib.request
from typing import Any, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5-coder:14b"


class OllamaAdapter(NexusComponent):
    """Adaptador para LLMs locais via Ollama.

    Métodos principais:
        execute(context) — interface NexusComponent padrão.
        is_available()   — verifica se o modelo configurado está disponível.
        list_local_models() — retorna lista de modelos instalados.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> None:
        self.model = model
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._available: Optional[bool] = None

    def configure(self, config: dict) -> None:
        """Suporte ao ciclo configure() do NexusComponent."""
        self.model = config.get("model", self.model)
        self.temperature = float(config.get("temperature", self.temperature))
        self.max_tokens = int(config.get("max_tokens", self.max_tokens))
        if "base_url" in config:
            self.base_url = config["base_url"].rstrip("/")
        self._available = None  # reset cache

    def execute(self, context: dict) -> dict:
        """Gera texto via Ollama.

        Campos aceitos em *context*:
            prompt (str, obrigatório)
            model (str) — sobrescreve self.model
            temperature (float)
            max_tokens (int)
            system (str) — system prompt opcional
            json_mode (bool) — se True, solicita resposta JSON
            task_type (str) — informativo, ignorado internamente
        """
        prompt = context.get("prompt")
        if not prompt:
            return {"success": False, "error": "Campo 'prompt' ausente"}
        model = context.get("model", self.model)
        temperature = float(context.get("temperature", self.temperature))
        max_tokens = int(context.get("max_tokens", self.max_tokens))
        try:
            response = self._generate(
                prompt,
                model=model,
                json_mode=context.get("json_mode", False),
                system=context.get("system"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return {"success": True, "response": response, "provider": "ollama", "model": model}
        except Exception as exc:
            logger.warning("OllamaAdapter falhou: %s", exc)
            return {"success": False, "error": str(exc), "provider": "ollama"}

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Retorna True se o servidor Ollama está acessível E o modelo configurado está instalado."""
        if self._available is not None:
            return self._available
        try:
            installed = self.list_local_models()
            self._available = any(
                m == self.model or m.split(":")[0] == self.model.split(":")[0]
                for m in installed
            )
        except Exception:
            self._available = False
        return self._available

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate(
        self,
        prompt: str,
        model: str,
        json_mode: bool = False,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Chama /api/generate com stream=false."""
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("response", "")

    # Backward-compatible alias used by existing code / tests
    def _chat(
        self,
        prompt: str,
        model: str,
        json_mode: bool = True,
        system: Optional[str] = None,
    ) -> str:
        """Legacy alias para _generate (mantido para compatibilidade com testes existentes)."""
        return self._generate(prompt, model=model, json_mode=json_mode, system=system)

    def list_local_models(self) -> list[str]:
        """Retorna os nomes dos modelos instalados no Ollama."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as resp:
                return [m["name"] for m in json.loads(resp.read())["models"]]
        except Exception:
            return []
