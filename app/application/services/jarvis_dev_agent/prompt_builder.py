# -*- coding: utf-8 -*-
"""PromptBuilder — Constrói prompts COM adapter registry."""
import json
import logging
from typing import Any, Dict, List
from app.core.nexus import nexus
from app.domain.models.agent import AgentTask
from .trajectory import AgentTrajectory

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Constrói prompts para o agente."""
    
    def __init__(self):
        self._adapter_registry = None
    
    def _get_adapter_registry(self):
        if self._adapter_registry is None:
            self._adapter_registry = nexus.resolve("adapter_registry")
        return self._adapter_registry
    
    def build(self, task: AgentTask, trajectory: AgentTrajectory, iteration: int) -> str:
        """Constrói prompt COM adapter registry."""
        working_memory = trajectory.get_working_memory() if trajectory.actions else "(Nenhuma ação)"
        adapters = self._get_adapters_list()
        gaps = self._detect_gaps(task.description)
        constraints = "\n".join(f"- {c}" for c in task.constraints) or "- Nenhuma"
        
        adapters_text = self._format_adapters(adapters)
        gaps_text = self._format_gaps(gaps)
        
        return f"""
🧠 VOCÊ É O JARVIS — AGENTE AUTÔNOMO DE DESENVOLVIMENTO

=== TAREFA ===
ID: {task.task_id} | Fonte: {task.source.value} | Prioridade: {task.priority.value}
Descrição: {task.description}
Critérios: {task.success_criteria}

=== ADAPTERS DISPONÍVEIS (Use estes em pipelines YAML) ===
{adapters_text}

=== GAPS DETECTADOS (Se precisar, crie estes adapters) ===
{gaps_text}

⚠️ FLUXO:
1. Se adapter existe → Crie pipeline YAML → Execute
2. Se adapter não existe → Crie adapter → Crie pipeline → Execute
=== RESTRIÇÕES ===
{constraints}

=== CONTEXTO ===
{json.dumps(task.context, default=str, indent=2)}

=== HISTÓRICO ===
{working_memory}

=== INSTRUÇÕES ===
Iteração {iteration}. Decida a PRÓXIMA ação.

1. **Consulte** adapters acima antes de criar código
2. **Crie pipeline YAML** quando possível
3. **Crie adapter** apenas se não existir
4. Retorne APENAS JSON:
{{
    "action_type": "create_pipeline" | "create_adapter" | "run_pipeline" | "read_file" | "edit_file" | "finish",
    "parameters": {{...}},
    "reasoning": "Por que esta ação agora"
}}

Retorne APENAS o JSON.
"""
    
    def _get_adapters_list(self) -> List[Dict[str, Any]]:
        try:
            registry = self._get_adapter_registry()
            if registry and not getattr(registry, "__is_cloud_mock__", False):
                result = registry.execute({"action": "list"})
                return result.get("adapters", [])
        except Exception as e:
            logger.debug(f"[PromptBuilder] Erro: {e}")
        return []
    
    def _detect_gaps(self, description: str) -> List[Dict[str, Any]]:
        try:
            registry = self._get_adapter_registry()
            if registry and not getattr(registry, "__is_cloud_mock__", False):
                result = registry.execute({"action": "find_gap", "capability": description})
                gap = result.get("gap")
                return [gap] if gap else []
        except Exception:
            pass
        return []
    
    def _format_adapters(self, adapters: List[Dict[str, Any]]) -> str:
        if not adapters:
            return "- Nenhum adapter registrado"        
        lines = []
        for adapter in adapters[:15]:
            lines.append(f"\n📦 {adapter['name']} ({adapter['adapter_id']})")
            lines.append(f"   Descrição: {adapter['description']}")
            lines.append(f"   Capabilities: {', '.join(adapter['capabilities'])}")
            lines.append(f"   Exemplo YAML:\n{adapter['example_yaml']}")
        return "\n".join(lines)
    
    def _format_gaps(self, gaps: List[Dict[str, Any]]) -> str:
        if not gaps:
            return "- Nenhum gap detectado"
        
        lines = []
        for gap in gaps:
            lines.append(f"\n⚠️ GAP: {gap['capability']}")
            lines.append(f"   Adapter sugerido: {gap['suggested_id']}")
        return "\n".join(lines)