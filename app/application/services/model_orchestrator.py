# -*- coding: utf-8 -*-
"""ModelOrchestrator — Orquestração de múltiplos LLMs com roteamento por complexidade.

Seleciona automaticamente o modelo mais adequado para cada requisição:
- Tarefa simples/rápida → Llama-3.2-3B (local, via Ollama)
- Tarefa de raciocínio/planejamento → Qwen-7B (local, via Ollama)
- Tarefa de embedding/memória → modelo de embeddings (local, via Ollama)
- Fallback automático local → cloud quando Ollama não está disponível.

O ModelOrchestrator também mantém um cache leve de respostas frequentes.
"""

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

# Modelos Ollama por perfil de tarefa
_MODEL_FAST = "llama3.2:3b"          # rápido: classificação, resposta curta
_MODEL_REASONING = "qwen2.5-coder:7b"  # raciocínio: análise, planejamento
_MODEL_EMBED = "nomic-embed-text"     # embeddings: busca semântica, memória

# Threshold de cache: respostas com até 10 min são reutilizadas
_CACHE_TTL_SECONDS = 600
_MAX_CACHE_SIZE = 200

# Tipos de tarefa mapeados para perfil de modelo
_COMPLEXITY_MAP: Dict[str, str] = {
    "classification": "fast",
    "intent": "fast",
    "summary": "fast",
    "translation": "fast",
    "code_repair": "reasoning",
    "code_generation": "reasoning",
    "planning": "reasoning",
    "evolution": "reasoning",
    "analysis": "reasoning",
    "embedding": "embed",
    "memory": "embed",
}


class ModelOrchestrator(NexusComponent):
    """Orquestra múltiplos LLMs locais (Ollama) com fallback para cloud.

    Fluxo de roteamento:
        1. Determina o perfil de modelo pela task_type.
        2. Verifica se o modelo Ollama está disponível.
        3. Se disponível, envia ao OllamaAdapter com o modelo correto.
        4. Se indisponível, faz fallback para AIGateway (cloud).
        5. Retorna resposta com metadados do modelo usado.
    """

    def __init__(self) -> None:
        self._response_cache: OrderedDict = OrderedDict()

    def configure(self, config: Dict[str, Any]) -> None:
        """Suporte ao ciclo configure() do NexusComponent."""
        pass  # nenhuma configuração estática necessária

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre pronto — fallback garante resposta."""
        return True

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Roteia e executa uma requisição de geração de texto.

        Campos aceitos em *context*:
            prompt (str, obrigatório) — texto de entrada.
            task_type (str) — tipo de tarefa para seleção do modelo.
            model (str) — sobrescreve a seleção automática de modelo.
            temperature (float) — temperatura de geração.
            max_tokens (int) — tokens máximos na resposta.
            system (str) — system prompt opcional.
            json_mode (bool) — resposta em JSON estruturado.
            use_cache (bool) — habilita cache de respostas. Padrão: True.

        Returns:
            Dicionário com ``success``, ``response``, ``provider`` e ``model``.
        """
        ctx = context or {}
        prompt = ctx.get("prompt", "")
        if not prompt:
            return {"success": False, "error": "Campo 'prompt' ausente"}

        task_type = ctx.get("task_type", "analysis")
        use_cache = ctx.get("use_cache", True)

        # Verifica cache
        if use_cache:
            cached = self._get_cached(prompt, task_type)
            if cached is not None:
                return {**cached, "from_cache": True}

        # Seleciona modelo
        profile = _COMPLEXITY_MAP.get(task_type, "reasoning")
        model_override = ctx.get("model")
        selected_model = model_override or self._select_model(profile)

        # Tenta Ollama local
        result = self._try_local(ctx, selected_model)
        if result.get("success"):
            if use_cache:
                self._set_cached(prompt, task_type, result)
            return result

        # Fallback para cloud
        logger.info(
            "[ModelOrchestrator] Ollama indisponível para '%s'. Usando fallback cloud.",
            selected_model,
        )
        return self._fallback_cloud(ctx)

    # ------------------------------------------------------------------
    # Routing helpers
    # ------------------------------------------------------------------

    def _select_model(self, profile: str) -> str:
        """Retorna o nome do modelo Ollama para o perfil informado."""
        return {
            "fast": _MODEL_FAST,
            "reasoning": _MODEL_REASONING,
            "embed": _MODEL_EMBED,
        }.get(profile, _MODEL_REASONING)

    def _try_local(self, ctx: Dict[str, Any], model: str) -> Dict[str, Any]:
        """Envia a requisição ao OllamaAdapter local."""
        try:
            ollama = nexus.resolve("ollama_adapter")
            if ollama is None:
                return {"success": False, "error": "ollama_adapter não disponível"}
            payload = {**ctx, "model": model}
            return ollama.execute(payload)
        except Exception as exc:
            logger.debug("[ModelOrchestrator] Ollama falhou: %s", exc)
            return {"success": False, "error": str(exc)}

    def _fallback_cloud(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Envia a requisição ao AIGateway (cloud) como fallback."""
        try:
            gateway = nexus.resolve("ai_gateway")
            if gateway is None:
                return {
                    "success": False,
                    "error": "ollama e ai_gateway indisponíveis",
                    "provider": "none",
                }
            return gateway.execute(ctx)
        except Exception as exc:
            logger.warning("[ModelOrchestrator] Fallback cloud falhou: %s", exc)
            return {"success": False, "error": str(exc), "provider": "none"}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, prompt: str, task_type: str) -> str:
        """Gera chave de cache SHA-256 truncada."""
        raw = f"{task_type}::{prompt}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _get_cached(self, prompt: str, task_type: str) -> Optional[Dict[str, Any]]:
        """Retorna resposta em cache se existir e não expirou."""
        key = self._cache_key(prompt, task_type)
        entry = self._response_cache.get(key)
        if entry is None:
            return None
        if time.time() - entry["cached_at"] > _CACHE_TTL_SECONDS:
            del self._response_cache[key]
            return None
        return entry["result"]

    def _set_cached(
        self, prompt: str, task_type: str, result: Dict[str, Any]
    ) -> None:
        """Armazena resultado no cache, respeitando o tamanho máximo (O(1) eviction)."""
        if len(self._response_cache) >= _MAX_CACHE_SIZE:
            # Remove a entrada mais antiga (FIFO — primeiro inserido)
            self._response_cache.popitem(last=False)
        key = self._cache_key(prompt, task_type)
        self._response_cache[key] = {"result": result, "cached_at": time.time()}
