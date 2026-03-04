# -*- coding: utf-8 -*-
"""
DecisionEngine — Motor de decisão baseado em snapshots .jrvs.

Responsabilidades:
  - Carrega snapshots .jrvs (llm, tools, meta) em memória na inicialização.
  - Expõe `decide(context)` para escolha de LLM/ferramenta baseada em políticas.
  - Se um módulo .jrvs estiver ausente, degrada graciosamente para o PolicyStore.
  - Expõe `reload_module(module_name)` para atualização incremental em memória.
  - Expõe `trigger_recompile(module_name)` para forçar recompilação via JRVSCompiler.
  - Retorna `DecisionResult` com o campo `jrvs_version` usado.

Variáveis de ambiente:
  JRVS_DIR   str   Diretório base dos arquivos .jrvs (default "data/jrvs").
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.meta.jrvs_compiler import JRVSCompiler
from app.core.meta.policy_store import PolicyStore
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

_INITIAL_MODULES = ("llm", "tools", "meta")


@dataclass
class DecisionResult:
    """Resultado de uma decisão tomada pelo DecisionEngine.

    Attributes:
        chosen: Identificador do LLM ou ferramenta escolhida.
        score: Pontuação calculada para a escolha.
        module: Módulo de onde a decisão foi derivada.
        jrvs_version: Versão do snapshot .jrvs utilizado (``"fallback"`` se PolicyStore).
        metadata: Informações extras sobre a decisão.
    """

    chosen: str
    score: float
    module: str
    jrvs_version: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


class DecisionEngine(NexusComponent):
    """Motor de decisão baseado em snapshots .jrvs.

    Args:
        compiler: Instância de JRVSCompiler.  Se ``None``, cria um novo.
        policy_store: Instância de PolicyStore.  Se ``None``, cria um novo.
    """

    def __init__(
        self,
        compiler: Optional[JRVSCompiler] = None,
        policy_store: Optional[PolicyStore] = None,
    ) -> None:
        self._compiler = compiler or JRVSCompiler(policy_store=policy_store)
        self._policy_store = policy_store or self._compiler._store
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._load_all_modules()

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa uma decisão baseada no contexto.

        Args:
            context: Dicionário de contexto (pode conter ``"command"``, ``"channel"``, etc.).

        Returns:
            Evidência de efeito com campos ``success``, ``chosen``, ``score``.
        """
        result = self.decide(context or {})
        return {
            "success": True,
            "chosen": result.chosen,
            "score": result.score,
            "module": result.module,
            "jrvs_version": result.jrvs_version,
        }

    # ------------------------------------------------------------------
    # Decision API
    # ------------------------------------------------------------------

    def decide(self, context: Dict[str, Any]) -> DecisionResult:
        """Escolhe o melhor LLM ou ferramenta para o *context* fornecido.

        Usa os snapshots .jrvs em memória; se ausentes, recorre ao PolicyStore.

        Args:
            context: Dicionário de contexto da requisição.

        Returns:
            :class:`DecisionResult` com a melhor opção identificada.
        """
        # Try jrvs snapshot for "llm" module first
        llm_snapshot = self._snapshots.get("llm")
        if llm_snapshot is None:
            llm_snapshot = self._fallback_load("llm")

        policies = (llm_snapshot or {}).get("policies", {})
        jrvs_version = (llm_snapshot or {}).get("meta", {}).get("compiler_version", "fallback")

        chosen, score = self._score_policies(policies, context)
        return DecisionResult(
            chosen=chosen,
            score=score,
            module="llm",
            jrvs_version=jrvs_version,
            metadata={"context_keys": list(context.keys())},
        )

    def register_feedback(self, decision_id: str, outcome: str) -> None:
        """Registra feedback sobre uma decisão anterior (EMA update).

        Args:
            decision_id: Identificador da decisão (geralmente o ``chosen`` retornado).
            outcome: ``"success"`` ou ``"failure"``.
        """
        policies = self._policy_store.get_policies_by_module("llm")
        entry = policies.get(decision_id, {})
        alpha = float(
            self._snapshots.get("meta", {}).get("policies", {}).get("learning_rate", 0.1)
        )
        if "meta" not in self._snapshots:
            logger.debug(
                "[DecisionEngine] Snapshot 'meta' ausente; usando learning_rate=0.1 padrão."
            )
        uses = entry.get("uses", 0) + 1
        prev_ema = entry.get("ema_success", 0.5)
        reward = 1.0 if outcome == "success" else 0.0
        ema = prev_ema + alpha * (reward - prev_ema)
        entry["uses"] = uses
        entry["ema_success"] = round(ema, 6)
        policies[decision_id] = entry
        self._policy_store.update_policies("llm", policies)
        # Refresh in-memory snapshot
        self.reload_module("llm")

    # ------------------------------------------------------------------
    # Module management
    # ------------------------------------------------------------------

    def reload_module(self, module_name: str) -> bool:
        """Recarrega o snapshot do módulo *module_name* a partir do arquivo .jrvs.

        Args:
            module_name: Nome do módulo.

        Returns:
            ``True`` se recarregado com sucesso, ``False`` em caso de falha.
        """
        try:
            data = self._compiler.read_module(module_name)
            self._snapshots[module_name] = data
            logger.info("[DecisionEngine] Snapshot '%s' recarregado da memória .jrvs.", module_name)
            return True
        except FileNotFoundError:
            logger.debug(
                "[DecisionEngine] Snapshot '%s' não encontrado; usando fallback.", module_name
            )
        except Exception as exc:
            logger.warning(
                "[DecisionEngine] Falha ao recarregar módulo '%s': %s", module_name, exc
            )
        return False

    def trigger_recompile(self, module_name: str) -> bool:
        """Força a recompilação do módulo *module_name* e recarrega o snapshot.

        Args:
            module_name: Nome do módulo.

        Returns:
            ``True`` se compilação e recarga foram bem-sucedidas.
        """
        try:
            self._compiler.compile_module(module_name)
            return self.reload_module(module_name)
        except Exception as exc:  # pragma: no cover
            logger.error(
                "[DecisionEngine] Falha ao recompilar módulo '%s': %s", module_name, exc
            )
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_all_modules(self) -> None:
        """Tenta carregar todos os módulos iniciais na memória."""
        for module_name in _INITIAL_MODULES:
            self.reload_module(module_name)

    def _fallback_load(self, module_name: str) -> Optional[Dict[str, Any]]:
        """Carrega políticas diretamente do PolicyStore (fallback sem .jrvs)."""
        policies = self._policy_store.get_policies_by_module(module_name)
        if policies:
            logger.info(
                "[DecisionEngine] Fallback PolicyStore ativo para módulo '%s'.", module_name
            )
            return {"policies": policies, "meta": {"compiler_version": "fallback"}}
        return None

    @staticmethod
    def _score_policies(
        policies: Dict[str, Any], context: Dict[str, Any]
    ) -> tuple:
        """Pontua as políticas disponíveis e retorna ``(chosen, score)``.

        Usa a métrica ``ema_success`` como proxy de qualidade.

        Args:
            policies: Dicionário de políticas por entidade.
            context: Contexto da requisição (reservado para extensões futuras).

        Returns:
            Tupla ``(chosen_id, score)`` com a melhor opção identificada.
        """
        if not policies:
            return ("default", 0.0)

        best_id = "default"
        best_score = -1.0
        for entity_id, attrs in policies.items():
            if not isinstance(attrs, dict):
                continue
            score = float(attrs.get("ema_success", 0.5))
            if score > best_score:
                best_score = score
                best_id = entity_id

        return (best_id, best_score)
