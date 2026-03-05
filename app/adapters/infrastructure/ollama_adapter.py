"""OllamaAdapter — LLMs locais via Ollama. API compatível com OpenAI."""
import json
import logging
import urllib.request
from typing import Any

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class OllamaAdapter(NexusComponent):
    def __init__(self, model: str = "qwen2.5-coder:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._available: bool | None = None

    def execute(self, context: dict) -> dict:
        prompt = context.get("prompt")
        if not prompt:
            return {"success": False, "error": "Campo 'prompt' ausente"}
        model = context.get("model", self.model)
        try:
            response = self._chat(
                prompt, model, context.get("json_mode", True), context.get("system")
            )
            return {"success": True, "response": response, "provider": "ollama", "model": model}
        except Exception as exc:
            logger.warning("OllamaAdapter falhou: %s", exc)
            return {"success": False, "error": str(exc), "provider": "ollama"}

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            req = urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=2)
            self._available = req.status == 200
        except Exception:
            self._available = False
        return self._available

    def _chat(
        self,
        prompt: str,
        model: str,
        json_mode: bool = True,
        system: str | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if json_mode:
            payload["format"] = "json"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]

    def list_local_models(self) -> list[str]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as resp:
                return [m["name"] for m in json.loads(resp.read())["models"]]
        except Exception:
            return []
