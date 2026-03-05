# -*- coding: utf-8 -*-
from app.core.nexus import NexusComponent
import os
import json
import requests
import re
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cooldown em segundos para provedores que retornaram HTTP 429
_RATE_LIMIT_COOLDOWN: Dict[str, float] = {}
_RATE_LIMIT_SECONDS = 30


class MetabolismCore(NexusComponent):
    """Client multi-LLM com fallback automático para a frota JARVIS."""

    # Frota de LLMs em ordem de prioridade
    _FLEET: List[Dict[str, Any]] = [
        {
            "name": "groq/llama-3.3-70b-versatile",
            "env": "GROQ_API_KEY",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "model": "llama-3.3-70b-versatile",
            "type": "openai",
            "json_mode": True,
        },
        {
            "name": "google/gemini-2.0-flash",
            "env": "GEMINI_API_KEY",
            "url": (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-2.0-flash:generateContent"
            ),
            "model": "gemini-2.0-flash",
            "type": "gemini",
            "json_mode": False,
        },
        {
            "name": "openrouter/deepseek-r1:free",
            "env": "OPENROUTER_API_KEY",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "model": "deepseek/deepseek-r1:free",
            "type": "openai",
            "json_mode": False,
            "extra_headers": {"HTTP-Referer": "https://github.com/TheDrack/Jarvis_Xerife"},
        },
        {
            "name": "openrouter/llama-3.3-70b:free",
            "env": "OPENROUTER_API_KEY",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "type": "openai",
            "json_mode": False,
            "extra_headers": {"HTTP-Referer": "https://github.com/TheDrack/Jarvis_Xerife"},
        },
        {
            "name": "mistral/mistral-small-latest",
            "env": "MISTRAL_API_KEY",
            "url": "https://api.mistral.ai/v1/chat/completions",
            "model": "mistral-small-latest",
            "type": "openai",
            "json_mode": False,
        },
        {
            "name": "groq/llama-3.1-8b-instant",
            "env": "GROQ_API_KEY",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "model": "llama-3.1-8b-instant",
            "type": "openai",
            "json_mode": True,
        },
    ]

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """NexusComponent entry-point: chama ask_jarvis com system/user prompt do contexto."""
        if not context:
            return {"success": False, "error": "context vazio"}
        system_prompt = context.get("system_prompt", "")
        user_prompt = context.get("user_prompt", "")
        require_json = context.get("require_json", True)
        try:
            result = self.ask_jarvis(system_prompt, user_prompt, require_json=require_json)
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("[MetabolismCore] Falha em execute(): %s", exc)
            return {"success": False, "error": str(exc)}

    def ask_jarvis(
        self,
        system_prompt: str,
        user_prompt: str,
        require_json: bool = True,
    ) -> Any:
        """Itera a frota e retorna a primeira resposta bem-sucedida."""
        last_error: Optional[Exception] = None

        for provider in self._FLEET:
            api_key = os.getenv(provider["env"], "")
            if not api_key:
                logger.debug("[MetabolismCore] Provedor %s sem key, pulando.", provider["name"])
                continue

            # Pula provedores em cooldown por rate-limit
            cooldown_until = _RATE_LIMIT_COOLDOWN.get(provider["name"], 0.0)
            if time.time() < cooldown_until:
                logger.debug(
                    "[MetabolismCore] Provedor %s em cooldown por rate-limit, pulando.",
                    provider["name"],
                )
                continue

            try:
                result = self._call_provider(
                    provider=provider,
                    api_key=api_key,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    require_json=require_json,
                )
                logger.info("[MetabolismCore] Resposta via %s.", provider["name"])
                return result
            except RateLimitError as exc:
                logger.warning("[MetabolismCore] Rate-limit em %s: %s", provider["name"], exc)
                _RATE_LIMIT_COOLDOWN[provider["name"]] = time.time() + _RATE_LIMIT_SECONDS
                last_error = exc
                continue
            except Exception as exc:
                logger.warning("[MetabolismCore] Erro em %s: %s", provider["name"], exc)
                last_error = exc
                continue

        raise Exception(
            f"Todos os provedores falharam. Último erro: {last_error}"
        )

    # ------------------------------------------------------------------
    # Métodos privados de chamada por tipo de provider
    # ------------------------------------------------------------------

    def _call_provider(
        self,
        provider: Dict[str, Any],
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        require_json: bool,
    ) -> Any:
        if provider["type"] == "gemini":
            return self._call_gemini(provider, api_key, system_prompt, user_prompt, require_json)
        return self._call_openai_compat(provider, api_key, system_prompt, user_prompt, require_json)

    def _call_openai_compat(
        self,
        provider: Dict[str, Any],
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        require_json: bool,
    ) -> Any:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        for k, v in provider.get("extra_headers", {}).items():
            headers[k] = v

        payload: Dict[str, Any] = {
            "model": provider["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        if require_json and provider.get("json_mode"):
            payload["response_format"] = {"type": "json_object"}

        resp = requests.post(provider["url"], headers=headers, json=payload, timeout=60)

        if resp.status_code == 429:
            raise RateLimitError(f"HTTP 429 em {provider['name']}")
        if resp.status_code != 200:
            # Groq: json_validate_failed → retry sem response_format
            if "json_validate_failed" in resp.text and "response_format" in payload:
                payload.pop("response_format")
                resp = requests.post(provider["url"], headers=headers, json=payload, timeout=60)
                if resp.status_code == 429:
                    raise RateLimitError(f"HTTP 429 em {provider['name']} (retry)")
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code} em {provider['name']}: {resp.text[:200]}")
            else:
                raise Exception(f"HTTP {resp.status_code} em {provider['name']}: {resp.text[:200]}")

        content = resp.json()["choices"][0]["message"]["content"]
        if require_json:
            return self._safe_json_decode(content)
        return content

    def _call_gemini(
        self,
        provider: Dict[str, Any],
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        require_json: bool,
    ) -> Any:
        url = f"{provider['url']}?key={api_key}"
        payload: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        if require_json:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        resp = requests.post(url, json=payload, timeout=60)

        if resp.status_code == 429:
            raise RateLimitError(f"HTTP 429 em {provider['name']}")
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code} em {provider['name']}: {resp.text[:200]}")

        content = (
            resp.json()
            .get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if require_json:
            return self._safe_json_decode(content)
        return content

    def _safe_json_decode(self, content: str) -> Any:
        """Extrai e limpa o JSON de strings sujas ou blocos markdown."""
        # Conteúdo vazio ou só espaços — falha rápida
        if not content or not content.strip():
            raise Exception("DNA corrompido para decodificação: conteúdo vazio recebido do LLM")

        # Tenta diretamente
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Remove blocos de markdown ```json ... ```
        clean = re.sub(r"```(?:json)?\s*", "", content).replace("```", "").strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

        # Tenta extrair o primeiro {...} (suporta JSON truncado com greedy match)
        match = re.search(r"(\{.*\})", clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # Limpeza agressiva de quebras de linha
        sanitized = content.replace("\n", "\\n").replace("\r", "\\r")
        try:
            return json.loads(sanitized)
        except Exception as exc:
            raise Exception(f"DNA corrompido para decodificação: {exc}") from exc


class RateLimitError(Exception):
    """Exceção específica para HTTP 429 de qualquer provedor."""
