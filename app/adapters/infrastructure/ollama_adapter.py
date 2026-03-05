# -*- coding: utf-8 -*-
"""OllamaAdapter — Adapter para LLM local via Ollama (localhost:11434)."""

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_OLLAMA_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"
_DEFAULT_TIMEOUT = 60


class OllamaAdapter(NexusComponent):
    """Adapter para comunicação com Ollama rodando localmente."""

    def __init__(
        self,
        base_url: str = _OLLAMA_BASE_URL,
        model: str = _DEFAULT_MODEL,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout = timeout

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Envia um prompt ao Ollama e retorna a resposta.

        Context keys:
            prompt (str): O prompt a ser enviado.
            system (str, optional): Mensagem de sistema.
            model (str, optional): Modelo a usar (sobrescreve o padrão).
            json_mode (bool, optional): Se True, solicita resposta JSON.

        Returns:
            dict: {"success": bool, "response": str} ou {"success": False, "error": str}
        """
        prompt = context.get("prompt", "")
        system = context.get("system", "")
        model = context.get("model", self._model)
        json_mode = context.get("json_mode", False)

        if not prompt:
            return {"success": False, "error": "prompt ausente no contexto"}

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        url = f"{self._base_url}/api/generate"

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)
                return {"success": True, "response": result.get("response", "")}
        except urllib.error.URLError as exc:
            logger.debug("Ollama indisponível em %s: %s", self._base_url, exc)
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.debug("Erro ao chamar Ollama: %s", exc)
            return {"success": False, "error": str(exc)}

    def is_available(self) -> bool:
        """Verifica se o Ollama está acessível em localhost."""
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False
