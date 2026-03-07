# -*- coding: utf-8 -*-
"""RewardSignalProvider — calcula rewards baseados em métricas reais.

Usado pelo EvolutionGatekeeper e FineTuneDatasetCollector para avaliar
qualidade de evoluções e interações.
"""
import json
import logging
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class RewardSignalProvider(NexusComponent):
    """Calcula rewards para evolução e interações."""
    
    def __init__(self):
        super().__init__()
        self._weights = {
            "tests": 0.4,
            "latency": 0.3,
            "errors": 0.2,
            "human": 0.1
        }
    
    def calculate_reward(self, before_state: dict, after_state: dict, 
                         human_approval: bool = True) -> float:
        """Calcula reward baseado em métricas reais de evolução."""
        
        # 1. Test pass rate (40%)
        tests_before = before_state.get("tests_passing_rate", 0.0)
        tests_after = after_state.get("tests_passing_rate", 0.0)
        test_delta = tests_after - tests_before
        test_score = self._weights["tests"] * (1.0 if test_delta >= 0 else max(0, 1 + test_delta))
        
        # 2. Latência delta (30%)
        latency_before = before_state.get("avg_latency_ms", 1000)
        latency_after = after_state.get("avg_latency_ms", 1000)
        if latency_after <= latency_before:
            latency_score = self._weights["latency"] * 1.0
        else:
            delta_pct = (latency_after - latency_before) / max(latency_before, 1)
            latency_score = self._weights["latency"] * max(0, 1 - delta_pct)
        
        # 3. Error rate (20%)
        errors_before = before_state.get("error_rate_24h", 0.0)
        errors_after = after_state.get("error_rate_24h", 0.0)
        if errors_after <= errors_before:
            error_score = self._weights["errors"] * 1.0
        else:            delta = errors_after - errors_before
            error_score = self._weights["errors"] * max(0, 1 - delta / 0.1)
        
        # 4. Feedback humano (10%)
        human_score = self._weights["human"] * (1.0 if human_approval else 0.0)
        
        reward = test_score + latency_score + error_score + human_score
        
        # Log para auditoria
        self._log_reward_calculation({
            "reward": reward,
            "breakdown": {
                "test_score": test_score,
                "latency_score": latency_score,
                "error_score": error_score,
                "human_score": human_score
            },
            "before_state": before_state,
            "after_state": after_state
        })
        
        return round(reward, 4)
    
    def calculate_interaction_reward(self, outcome: str, feedback: Optional[str]) -> float:
        """Calcula reward para interações de interface (Telegram/HUD).
        
        ADIÇÃO: Método novo para integração com interfaces.
        """
        base = {"executed": 0.8, "clarified": 0.5, "rejected": 0.2}
        reward = base.get(outcome, 0.3)
        
        if feedback:
            feedback_lower = feedback.lower()
            if any(p in feedback_lower for p in ["👍", "bom", "ótimo", "great", "good"]):
                reward += 0.1
            elif any(p in feedback_lower for p in ["👎", "ruim", "lento", "bad", "wrong"]):
                reward -= 0.1
        
        return max(0.0, min(1.0, round(reward, 4)))
    
    def _log_reward_calculation(self, data: dict):
        """Registra cálculo no ThoughtLog para auditoria."""
        thought_log = nexus.resolve("thought_log_service")
        if thought_log:
            thought_log.record({
                "event": "reward_calculated",
                **data
            })
    
    async def optimize_weights_with_llm(self, history: List[dict]) -> dict:        """LLM sugere pesos ideais baseado em padrões históricos."""
        llm_router = nexus.resolve("llm_router")
        if llm_router is None:
            return self._weights
        
        successes = sum(1 for h in history if h.get("reward", 0) >= 0.7)
        failures = sum(1 for h in history if h.get("reward", 0) < 0.5)
        
        prompt = f"""Analise {len(history)} ciclos de evolução:
- Sucessos (reward >= 0.7): {successes}
- Falhas (reward < 0.5): {failures}

Sugira pesos para: tests, latency, errors, human_feedback
A soma deve ser 1.0.
Retorne apenas JSON: {{"tests": 0.X, "latency": 0.X, "errors": 0.X, "human": 0.X}}"""
        
        try:
            result = await llm_router.execute({
                "prompt": prompt,
                "task_type": "reward_optimization",
                "require_json": True
            })
            
            new_weights = json.loads(result.get("response", "{}"))
            if sum(new_weights.values()) > 0:
                total = sum(new_weights.values())
                self._weights = {k: round(v / total, 2) for k, v in new_weights.items()}
                logger.info("[RewardProvider] Pesos otimizados: %s", self._weights)
            
            return self._weights
        except Exception as e:
            logger.warning("[RewardProvider] Otimização falhou: %s", e)
            return self._weights
    
    def update_weights(self, new_weights: dict):
        """Atualiza pesos manualmente."""
        self._weights = new_weights
        logger.info("[RewardProvider] Pesos atualizados: %s", self._weights)