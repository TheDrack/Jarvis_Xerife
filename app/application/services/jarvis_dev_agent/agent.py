# -*- coding: utf-8 -*-
"""JarvisDevAgent — Agente autônomo principal."""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent, nexus
from app.domain.models.agent import AgentAction, AgentTask, TaskSource, TaskPriority

from .trajectory import AgentTrajectory
from .actions import ActionExecutor
from .prompt_builder import PromptBuilder
from .pipeline_builder import PipelineBuilder

logger = logging.getLogger(__name__)

_JOBS_FILE = Path("data/dev_agent_jobs.jsonl")
_MAX_ITERATIONS = 15


class JarvisDevAgent(NexusComponent):
    """Agente autônomo que usa AdapterRegistry + Pipeline Runner."""
    
    def __init__(self) -> None:
        super().__init__()
        self.max_iterations: int = _MAX_ITERATIONS
        self._trajectory: Optional[AgentTrajectory] = None
        self._executor = ActionExecutor()
        self._prompt_builder = PromptBuilder()
        self._pipeline_builder = PipelineBuilder()
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa tarefa autônoma."""
        ctx = context or {}
        task = self._create_task(ctx)
        
        logger.info(f"🤖 [JarvisDevAgent] task_id={task.task_id} source={task.source.value}")
        
        self._trajectory = AgentTrajectory(task=task)
        
        try:
            result = self._run_cycle(task)
            self._consolidate(result)
            return result
        except Exception as e:
            logger.error(f"❌ [JarvisDevAgent] Erro: {e}", exc_info=True)            return {"success": False, "task_id": task.task_id, "reason": str(e)}
    
    def _create_task(self, ctx: Dict[str, Any]) -> AgentTask:
        return AgentTask(
            task_id=ctx.get("task_id", f"task_{uuid.uuid4().hex[:12]}"),
            source=TaskSource(ctx.get("source", "user_request")),
            priority=TaskPriority(ctx.get("priority", "medium")),
            description=ctx.get("description", ""),
            context=ctx.get("context", {}),
            constraints=ctx.get("constraints", []),
            success_criteria=ctx.get("success_criteria", "Tarefa completada"),
        )
    
    def _run_cycle(self, task: AgentTask) -> Dict[str, Any]:
        iteration = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"🔄 Iteração {iteration}/{self.max_iterations}")
            
            prompt = self._prompt_builder.build(task, self._trajectory, iteration)
            action = self._decide_action(prompt)
            
            if not action:
                return self._fail(task.task_id, "LLM não retornou ação válida", iteration)
            
            logger.info(f"🎯 Ação: {action.action_type.value} - {action.reasoning[:100]}")
            
            observation = self._executor.execute(action)
            self._trajectory.add_step(action, observation)
            
            if action.action_type.value == "finish":
                return self._success(task.task_id, task, iteration, observation.output)
            
            if not observation.success and self._is_critical(observation):
                return self._fail(task.task_id, f"Falha crítica: {observation.error}", iteration)
        
        return self._fail(task.task_id, f"Limite de {self.max_iterations} iterações", iteration)
    
    def _decide_action(self, prompt: str) -> Optional[AgentAction]:
        try:
            router = nexus.resolve("llm_router")
            if not router or getattr(router, "__is_cloud_mock__", False):
                return None
            
            result = router.execute({
                "task_type": "code_generation",
                "prompt": prompt,
                "require_json": True,
                "temperature": 0.1,            })
            
            response = result.get("result", result.get("response", ""))
            json_str = self._extract_json(response)
            if not json_str:
                return None
            
            data = json.loads(json_str)
            return AgentAction(
                action_type=ActionType(data.get("action_type", "finish")),
                parameters=data.get("parameters", {}),
                reasoning=data.get("reasoning", ""),
                step_number=len(self._trajectory.actions) + 1,
            )
        except Exception as e:
            logger.error(f"❌ Erro ao decidir ação: {e}")
            return None
    
    def _extract_json(self, response: str) -> Optional[str]:
        match = re.search(r'```(?:json)?\s*({.*?})\s*```', response, re.DOTALL)
        if match:
            return match.group(1)
        try:
            start, end = response.find("{"), response.rfind("}") + 1
            if start >= 0 and end > start:
                return response[start:end]
        except Exception:
            pass
        return None
    
    def _is_critical(self, observation) -> bool:
        if not observation.error:
            return False
        critical = ["permission denied", "no such file", "syntax error", "import error"]
        return any(ind in observation.error.lower() for ind in critical)
    
    def _success(self, task_id: str, task: AgentTask, iterations: int, output: str) -> Dict[str, Any]:
        self._trajectory.success = True
        self._trajectory.final_result = output
        self._trajectory.completed_at = datetime.now(timezone.utc)
        self._record_learning(task)
        
        return {
            "success": True,
            "task_id": task_id,
            "task_source": task.source.value,
            "iterations": iterations,
            "trajectory": self._trajectory.to_dict(),
            "final_output": output[:500],
        }    
    def _fail(self, task_id: str, reason: str, iterations: int) -> Dict[str, Any]:
        if self._trajectory:
            self._trajectory.success = False
            self._trajectory.final_result = reason
            self._trajectory.completed_at = datetime.now(timezone.utc)
        
        return {
            "success": False,
            "task_id": task_id,
            "reason": reason,
            "iterations": iterations,
            "trajectory": self._trajectory.to_dict() if self._trajectory else None,
        }
    
    def _consolidate(self, result: Dict[str, Any]) -> None:
        try:
            _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "task_id": result.get("task_id"),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "success": result.get("success", False),
                "source": result.get("task_source"),
            }
            with open(_JOBS_FILE, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
    
    def _record_learning(self, task: AgentTask) -> None:
        try:
            memory = nexus.resolve("procedural_memory")
            if memory and not getattr(memory, "__is_cloud_mock__", False):
                memory.execute({
                    "action": "store_pattern",
                    "command_pattern": f"{task.source.value}_{task.description[:50]}",
                    "task_type": f"dev_agent_{task.source.value}",
                    "solution": self._trajectory.final_result,
                    "success": True,
                    "confidence": 0.8,
                })
        except Exception:
            pass
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True