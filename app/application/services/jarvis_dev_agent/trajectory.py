# -*- coding: utf-8 -*-
"""Trajectory — Gerencia histórico de ações do agente."""
from datetime import datetime, timezone
from typing import List, Optional
from app.domain.models.agent import AgentAction, AgentObservation, AgentTask


class AgentTrajectory:
    """Histórico completo de uma sessão de agente."""
    
    def __init__(self, task: AgentTask):
        self.task = task
        self.actions: List[AgentAction] = []
        self.observations: List[AgentObservation] = []
        self.success: bool = False
        self.final_result: str = ""
        self.started_at: datetime = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
    
    def add_step(self, action: AgentAction, observation: AgentObservation) -> None:
        """Adiciona par ação-observação à trajetória."""
        self.actions.append(action)
        self.observations.append(observation)
    
    def get_working_memory(self) -> str:
        """Gera representação em texto para prompt."""
        lines = ["=== HISTÓRICO DE AÇÕES ==="]
        for i, (action, obs) in enumerate(zip(self.actions, self.observations), 1):
            lines.append(f"\n--- Passo {i} ---")
            lines.append(f"Ação: {action.action_type.value}")
            lines.append(f"Razão: {action.reasoning[:100]}")
            lines.append(f"Resultado: {'✅' if obs.success else '❌'}")
            output_preview = obs.output[:300] + "..." if len(obs.output) > 300 else obs.output
            lines.append(f"Saída: {output_preview}")
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """Serializa para dicionário."""
        return {
            "task": self.task.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "observations": [o.to_dict() for o in self.observations],
            "success": self.success,
            "final_result": self.final_result,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_steps": len(self.actions),
        }