# -*- coding: utf-8 -*-
"""
DecisionEngine — Motor de decisão adaptativo baseado em snapshots .jrvs.

Responsabilidades:
  - Carrega snapshots .jrvs (llm, tools, meta) em memória na inicialização.
  - Expõe `decide(context)` com scoring multi-objetivo ponderado.
  - Epsilon-greedy adaptativo: ajusta exploração com base no global_success_ema.
  - Demoção automática e quarentena de políticas com alta taxa de falha.
  - Guardrail de estabilidade: quando global_success_ema < 0.4 entra em modo de
    segurança (congela epsilon, suspende promoções e demoções).
  - Degrada graciosamente ao PolicyStore se .jrvs ausente ou schema incompatível.

Variáveis de ambiente:
  JRVS_DIR        str    Diretório base dos arquivos .jrvs (default "data/jrvs").
  W_SUCCESS       float  Peso de ema_success no scoring (default 0.5).
  W_FAILURE       float  Peso de failure_rate no scoring (default 0.2).
  W_LATENCY       float  Peso de latência normalizada (default 0.1).
  W_CONFIDENCE    float  Peso de confidence (default 0.1).
  W_COST          float  Peso de custo (default 0.1).
"""

import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from app.core.meta.jrvs_compiler import JRVSCompiler, SchemaVersionError
from app.core.meta.policy_store import PolicyStore
from app.core.nexuscomponent import NexusComponent

logger = logging.getLogger(__name__)

_INITIAL_MODULES = ("llm", "tools", "meta")

# Stability threshold: below this global_success_ema the engine enters safety mode
_STABILITY_THRESHOLD = 0.4
_STABILITY_EPSILON = 0.3

# Default epsilon parameters (read from meta module at runtime)
_DEFAULT_EPSILON = 0.15
_DEFAULT_DECAY = 0.995
_DEFAULT_MIN_EPSILON = 0.03
_DEFAULT_MAX_EPSILON = 0.4
_DEFAULT_GLOBAL_SUCCESS_EMA = 0.8
_DEFAULT_LEARNING_RATE = 0.1

# Demotion thresholds
_DEMOTE_MIN_TOTAL = 5
_DEMOTE_FAILURE_RATE = 0.6
_QUARANTINE_MIN_TOTAL = 10
_QUARANTINE_FAILURE_RATE = 0.75
_RECOVERY_CONSECUTIVE = 3


@dataclass
class DecisionResult:
    """Resultado de uma decisão tomada pelo DecisionEngine.

    Attributes:
        chosen: Identificador do LLM ou ferramenta escolhida.
        score: Pontuação calculada para a escolha.
        module: Módulo de onde a decisão foi derivada.
        jrvs_version: Versão do snapshot .jrvs utilizado (``"fallback"`` se PolicyStore).
        exploration: Se a decisão foi por exploração epsilon-greedy.
        epsilon: Valor de epsilon no momento da decisão.
        global_success_ema: EMA global de sucesso no momento da decisão.
        metadata: Informações extras sobre a decisão.
    """

    chosen: str
    score: float
    module: str
    jrvs_version: str = "unknown"
    exploration: bool = False
    epsilon: float = _DEFAULT_EPSILON
    global_success_ema: float = _DEFAULT_GLOBAL_SUCCESS_EMA
    metadata: Dict[str, Any] = field(default_factory=dict)


class DecisionEngine(NexusComponent):
    """Motor de decisão adaptativo baseado em snapshots .jrvs.

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
        self._snapshot_versions: Dict[str, str] = {}
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
            "exploration": result.exploration,
            "epsilon": result.epsilon,
            "global_success_ema": result.global_success_ema,
        }

    # ------------------------------------------------------------------
    # Decision API
    # ------------------------------------------------------------------

    def decide(self, context: Dict[str, Any]) -> DecisionResult:
        """Escolhe o melhor LLM ou ferramenta para o *context* fornecido.

        Usa scoring multi-objetivo ponderado com epsilon-greedy adaptativo.
        Degrada graciosamente ao PolicyStore se .jrvs ausente ou schema incompatível.

        Args:
            context: Dicionário de contexto da requisição.

        Returns:
            :class:`DecisionResult` com a melhor opção identificada.
        """
        llm_snapshot = self._snapshots.get("llm")
        if llm_snapshot is None:
            llm_snapshot = self._fallback_load("llm")

        policies = (llm_snapshot or {}).get("policies", {})
        jrvs_version = (llm_snapshot or {}).get("meta", {}).get("compiler_version", "fallback")

        meta_params = self._get_meta_params()
        epsilon = meta_params["epsilon"]
        global_success_ema = meta_params["global_success_ema"]

        stability = self.get_stability_state()
        if stability == "critical":
            epsilon = _STABILITY_EPSILON

        # Epsilon-greedy exploration
        exploration = False
        candidates = [
            eid for eid, attrs in policies.items()
            if isinstance(attrs, dict) and not attrs.get("quarantined")
        ]

        if candidates and random.random() < epsilon:
            chosen = random.choice(candidates)
            score = float(policies[chosen].get("ema_success", 0.5))
            exploration = True
        else:
            chosen, score = self._score_policies(policies, context)

        logger.info(
            "[DecisionEngine] chosen=%s score=%.4f exploration=%s epsilon=%.4f "
            "global_success_ema=%.4f jrvs_version=%s",
            chosen,
            score,
            exploration,
            epsilon,
            global_success_ema,
            jrvs_version,
        )

        return DecisionResult(
            chosen=chosen,
            score=score,
            module="llm",
            jrvs_version=jrvs_version,
            exploration=exploration,
            epsilon=epsilon,
            global_success_ema=global_success_ema,
            metadata={"context_keys": list(context.keys())},
        )

    def register_feedback(self, decision_id: str, outcome: str) -> None:
        """Registra feedback sobre uma decisão anterior.

        Atualiza:
          - EMA de sucesso, contadores de sucesso/falha
          - Demoção e quarentena automáticas (se não em stability mode)
          - Recuperação de quarentena por sucessos consecutivos
          - global_success_ema e epsilon adaptativo no módulo meta

        Args:
            decision_id: Identificador da decisão (geralmente o ``chosen`` retornado).
            outcome: ``"success"`` ou ``"failure"``.
        """
        stability = self.get_stability_state()
        policies = self._policy_store.get_policies_by_module("llm")
        entry = policies.get(decision_id, {})

        meta_params = self._get_meta_params()
        alpha = meta_params["learning_rate"]

        # Update success/failure counters
        is_success = outcome == "success"
        entry["uses"] = entry.get("uses", 0) + 1
        entry["success_count"] = entry.get("success_count", 0) + (1 if is_success else 0)
        entry["failure_count"] = entry.get("failure_count", 0) + (0 if is_success else 1)

        # EMA update
        prev_ema = entry.get("ema_success", 0.5)
        reward = 1.0 if is_success else 0.0
        entry["ema_success"] = round(prev_ema + alpha * (reward - prev_ema), 6)

        # Consecutive successes tracking (for quarantine recovery)
        if is_success:
            entry["consecutive_successes"] = entry.get("consecutive_successes", 0) + 1
        else:
            entry["consecutive_successes"] = 0

        # Auto-recovery from quarantine
        if entry.get("quarantined") and entry.get("consecutive_successes", 0) >= _RECOVERY_CONSECUTIVE:
            entry.pop("quarantined", None)
            entry["confidence"] = 0.5
            entry["consecutive_successes"] = 0
            logger.info(
                "[DecisionEngine] Política '%s' recuperada da quarentena.", decision_id
            )

        # Demotion and quarantine (only outside stability mode)
        if stability != "critical":
            total = entry["success_count"] + entry["failure_count"]
            failure_rate = entry["failure_count"] / max(1, total)

            if total >= _QUARANTINE_MIN_TOTAL and failure_rate > _QUARANTINE_FAILURE_RATE:
                if not entry.get("quarantined"):
                    entry["quarantined"] = True
                    entry["confidence"] = 0.1
                    logger.warning(
                        "[DecisionEngine] Política '%s' movida para quarentena "
                        "(failure_rate=%.2f, total=%d).",
                        decision_id,
                        failure_rate,
                        total,
                    )
            elif total >= _DEMOTE_MIN_TOTAL and failure_rate > _DEMOTE_FAILURE_RATE:
                old_conf = entry.get("confidence", 1.0)
                entry["confidence"] = round(old_conf * 0.5, 6)
                logger.info(
                    "[DecisionEngine] Política '%s' demovida "
                    "(confidence %.2f → %.2f, failure_rate=%.2f).",
                    decision_id,
                    old_conf,
                    entry["confidence"],
                    failure_rate,
                )

        policies[decision_id] = entry
        self._policy_store.update_policies("llm", policies)

        # Update adaptive epsilon via meta module
        self._update_adaptive_epsilon(is_success)

        # Refresh in-memory snapshots
        self.reload_module("llm")

    def get_stability_state(self) -> str:
        """Retorna o estado de estabilidade do motor de decisão.

        Returns:
            ``"ok"`` quando global_success_ema >= 0.4, ``"critical"`` caso contrário.
        """
        meta_params = self._get_meta_params()
        gse = meta_params["global_success_ema"]
        if gse < _STABILITY_THRESHOLD:
            logger.critical(
                "[DecisionEngine] STABILITY MODE ATIVO: global_success_ema=%.4f < %.1f. "
                "Epsilon congelado em %.1f. Promoções e demoções suspensas.",
                gse,
                _STABILITY_THRESHOLD,
                _STABILITY_EPSILON,
            )
            return "critical"
        return "ok"

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
            ver = data.get("meta", {}).get("compiler_version", "?")
            self._snapshot_versions[module_name] = ver
            logger.info(
                "[DecisionEngine] Snapshot '%s' recarregado (version=%s).", module_name, ver
            )
            return True
        except FileNotFoundError:
            logger.debug(
                "[DecisionEngine] Snapshot '%s' não encontrado; usando fallback.", module_name
            )
        except SchemaVersionError as exc:
            logger.warning(
                "[DecisionEngine] Schema incompatível para '%s': %s. Usando fallback.",
                module_name,
                exc,
            )
        except Exception as exc:
            logger.warning(
                "[DecisionEngine] Falha ao recarregar módulo '%s': %s", module_name, exc
            )
        self._snapshots.pop(module_name, None)
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

    def _get_meta_params(self) -> Dict[str, float]:
        """Retorna os parâmetros meta (epsilon, decay, etc.).

        Lê diretamente do PolicyStore para garantir valores atualizados (meta é
        atualizado a cada ``register_feedback``).  Usa o snapshot .jrvs como
        fallback se o PolicyStore estiver vazio.
        """
        # Read live from PolicyStore — meta changes on every register_feedback
        policies = self._policy_store.get_policies_by_module("meta")
        if not policies:
            # Fall back to .jrvs snapshot when PolicyStore has no meta yet
            meta_snapshot = self._snapshots.get("meta")
            if meta_snapshot is None:
                meta_snapshot = self._fallback_load("meta")
            policies = (meta_snapshot or {}).get("policies", {})
        return {
            "epsilon": float(policies.get("epsilon", _DEFAULT_EPSILON)),
            "decay": float(policies.get("decay", _DEFAULT_DECAY)),
            "min_epsilon": float(policies.get("min_epsilon", _DEFAULT_MIN_EPSILON)),
            "max_epsilon": float(policies.get("max_epsilon", _DEFAULT_MAX_EPSILON)),
            "global_success_ema": float(
                policies.get("global_success_ema", _DEFAULT_GLOBAL_SUCCESS_EMA)
            ),
            "learning_rate": float(policies.get("learning_rate", _DEFAULT_LEARNING_RATE)),
        }

    def _update_adaptive_epsilon(self, is_success: bool) -> None:
        """Atualiza global_success_ema e epsilon adaptativo no módulo meta."""
        meta_policies = self._policy_store.get_policies_by_module("meta")
        p = self._get_meta_params()

        # Update global_success_ema
        reward = 1.0 if is_success else 0.0
        gse = p["global_success_ema"] + p["learning_rate"] * (reward - p["global_success_ema"])
        meta_policies["global_success_ema"] = round(gse, 6)

        # Adaptive epsilon adjustment (skipped in stability mode — epsilon frozen by decide())
        if gse >= _STABILITY_THRESHOLD:
            if gse < 0.6:
                eps = min(p["max_epsilon"], p["epsilon"] * 1.05)
            else:
                eps = max(p["min_epsilon"], p["epsilon"] * p["decay"])
            meta_policies["epsilon"] = round(eps, 6)

        self._policy_store.update_policies("meta", meta_policies)
        # Refresh meta snapshot
        self.reload_module("meta")

    @staticmethod
    def _score_policies(
        policies: Dict[str, Any], context: Dict[str, Any]
    ) -> Tuple[str, float]:
        """Pontua as políticas disponíveis com scoring multi-objetivo ponderado.

        score = w_success * ema_success
              - w_failure * failure_rate
              + w_latency * norm_latency
              + w_confidence * confidence
              - w_cost * cost_penalty

        Onde:
          - norm_latency  = 1 / (1 + avg_latency)
          - failure_rate  = failure_count / max(1, success+failure)

        Políticas em quarentena são ignoradas.

        Args:
            policies: Dicionário de políticas por entidade.
            context: Contexto da requisição (reservado para extensões futuras).

        Returns:
            Tupla ``(chosen_id, score)`` com a melhor opção identificada.
        """
        if not policies:
            return ("default", 0.0)

        w_success = float(os.getenv("W_SUCCESS", "0.5"))
        w_failure = float(os.getenv("W_FAILURE", "0.2"))
        w_latency = float(os.getenv("W_LATENCY", "0.1"))
        w_confidence = float(os.getenv("W_CONFIDENCE", "0.1"))
        w_cost = float(os.getenv("W_COST", "0.1"))

        best_id = "default"
        best_score = float("-inf")

        for entity_id, attrs in policies.items():
            if not isinstance(attrs, dict):
                continue
            if attrs.get("quarantined"):
                continue

            ema_success = float(attrs.get("ema_success", 0.5))
            success_c = float(attrs.get("success_count", 0))
            failure_c = float(attrs.get("failure_count", 0))
            failure_rate = failure_c / max(1.0, success_c + failure_c)
            avg_latency = float(attrs.get("avg_latency", 0.0))
            norm_latency = 1.0 / (1.0 + avg_latency)
            confidence = float(attrs.get("confidence", 1.0))
            cost_penalty = float(attrs.get("cost_estimate", 0.0))

            score = (
                w_success * ema_success
                - w_failure * failure_rate
                + w_latency * norm_latency
                + w_confidence * confidence
                - w_cost * cost_penalty
            )

            if score > best_score:
                best_score = score
                best_id = entity_id

        if best_id == "default":
            return ("default", 0.0)

        return (best_id, best_score)
