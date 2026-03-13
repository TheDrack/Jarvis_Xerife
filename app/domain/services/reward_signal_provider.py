# -*- coding: utf-8 -*-
""" RewardSignalProvider — calcula rewards baseados em métricas reais.

Versão 2026.03: Corrigida para estabilidade matemática e integração Nexus.
"""
import json
import logging
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class RewardSignalProvider(NexusComponent):
    """Calcula rewards (recompensas) para evolução de código e interações de usuário."""

    def __init__(self):
        super().__init__()
        # Pesos padrão calibrados para o JARVIS DNA
        self._weights = {
            "tests": 0.4,   # Importância da estabilidade funcional
            "latency": 0.3, # Eficiência de execução
            "errors": 0.2,  # Confiabilidade em runtime
            "human": 0.1    # Validação subjetiva
        }

    def calculate_reward(self, before_state: dict, after_state: dict, 
                         human_approval: bool = True) -> float:
        """Calcula reward baseado em métricas reais comparativas de evolução."""

        # 1. Test pass rate (40%)
        # Premissa: Se os testes caírem, o reward deve sofrer uma penalidade severa.
        tests_before = before_state.get("tests_passing_rate", 0.0)
        tests_after = after_state.get("tests_passing_rate", 0.0)
        test_delta = tests_after - tests_before
        
        if test_delta >= 0:
            test_score = self._weights["tests"] * tests_after
        else:
            # Penaliza proporcionalmente à queda
            test_score = self._weights["tests"] * max(0.0, tests_after + test_delta)

        # 2. Latência delta (30%)
        # Premissa: Recompensar código mais rápido.
        latency_before = max(1, before_state.get("avg_latency_ms", 1000))
        latency_after = max(1, after_state.get("avg_latency_ms", 1000))
        
        if latency_after <= latency_before:
            latency_score = self._weights["latency"] * 1.0
        else:
            # Penaliza o aumento de latência
            delta_pct = (latency_after - latency_before) / latency_before
            latency_score = self._weights["latency"] * max(0.0, 1.0 - delta_pct)

        # 3. Error rate (20%)
        # Premissa: Queda na taxa de erros de 24h.
        errors_before = before_state.get("error_rate_24h", 0.0)
        errors_after = after_state.get("error_rate_24h", 0.0)
        
        if errors_after <= errors_before:
            error_score = self._weights["errors"] * 1.0
        else:
            delta = errors_after - errors_before
            # Escala de sensibilidade: 0.1 (10%) de aumento zera o score de erro
            error_score = self._weights["errors"] * max(0.0, 1.0 - (delta / 0.1))

        # 4. Feedback humano (10%)
        human_score = self._weights["human"] * (1.0 if human_approval else 0.0)

        reward = test_score + latency_score + error_score + human_score

        # Registro para auditoria do ThoughtLog
        self._log_reward_calculation({
            "reward_final": round(reward, 4),
            "breakdown": {
                "test_score": round(test_score, 4),
                "latency_score": round(latency_score, 4),
                "error_score": round(error_score, 4),
                "human_score": round(human_score, 4)
            },
            "metrics_delta": {
                "test_diff": round(test_delta, 4),
                "latency_diff_ms": latency_after - latency_before
            }
        })

        return round(float(reward), 4)

    def calculate_interaction_reward(self, outcome: str, feedback: Optional[str]) -> float:
        """Calcula reward para interações rápidas (API/Interface)."""
        base_map = {"executed": 0.8, "clarified": 0.5, "rejected": 0.2}
        reward = base_map.get(outcome, 0.3)

        if feedback:
            f_lower = feedback.lower()
            # Positivos
            if any(p in f_lower for p in ["👍", "bom", "ótimo", "great", "good", "perfeito"]):
                reward += 0.15
            # Negativos
            elif any(p in f_lower for p in ["👎", "ruim", "lento", "bad", "wrong", "erro"]):
                reward -= 0.2

        return max(0.0, min(1.0, round(float(reward), 4)))

    def _log_reward_calculation(self, data: dict):
        """Notifica o serviço de ThoughtLog para manter rastreabilidade evolutiva."""
        try:
            thought_log = nexus.resolve("thought_log_service")
            if thought_log and not getattr(thought_log, "__is_cloud_mock__", False):
                thought_log.record({
                    "component": "RewardSignalProvider",
                    "event": "reward_calculation_audit",
                    "payload": data
                })
        except Exception as e:
            logger.debug("Falha silenciosa ao logar reward: %s", e)

    async def optimize_weights_with_llm(self, history: List[dict]) -> dict:
        """Utiliza o LLM para ajustar os pesos baseando-se no que gerou mais sucesso."""
        llm_router = nexus.resolve("llm_router")
        if not llm_router or getattr(llm_router, "__is_cloud_mock__", False):
            return self._weights

        successes = sum(1 for h in history if h.get("reward_final", 0) >= 0.7)
        failures = sum(1 for h in history if h.get("reward_final", 0) < 0.5)

        prompt = f"""Analise os pesos atuais: {self._weights}
Contexto: {len(history)} ciclos processados. Sucessos: {successes}, Falhas: {failures}.
Sugira novos pesos para (tests, latency, errors, human) que priorizem a estabilidade do sistema.
A soma deve ser exatamente 1.0. 
Retorne APENAS um JSON válido."""

        try:
            result = await llm_router.execute({
                "prompt": prompt,
                "require_json": True
            })

            # Tenta extrair e validar JSON da resposta do LLM
            raw_response = result.get("response", "{}")
            new_weights = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
            
            if isinstance(new_weights, dict) and all(k in new_weights for k in self._weights):
                total = sum(new_weights.values())
                if total > 0:
                    # Normalização para garantir que a soma seja 1.0
                    self._weights = {k: round(v / total, 2) for k, v in new_weights.items()}
                    logger.info("[NEXUS REWARD] Pesos otimizados via LLM: %s", self._weights)

            return self._weights
        except Exception as e:
            logger.warning("[NEXUS REWARD] Falha na otimização de pesos: %s", e)
            return self._weights

    def update_weights(self, new_weights: dict):
        """Atualização manual de pesos por admin ou protocolo de emergência."""
        if abs(sum(new_weights.values()) - 1.0) < 0.01:
            self._weights = new_weights
            logger.info("[NEXUS REWARD] Pesos atualizados manualmente: %s", self._weights)
        else:
            logger.error("[NEXUS REWARD] Falha ao atualizar: Pesos não somam 1.0")

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Contrato Nexus para execução via contexto."""
        if not context:
            return {"success": False, "error": "Contexto vazio"}
            
        action = context.get("action")
        if action == "calculate_interaction":
            res = self.calculate_interaction_reward(
                outcome=context.get("outcome", "unknown"),
                feedback=context.get("feedback")
            )
            return {"success": True, "reward": res}
            
        return {"success": False, "error": f"Ação '{action}' não suportada"}
