# -*- coding: utf-8 -*-
"""Agent Models — Estruturas para Action-Observation Loop."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


class ActionType(str, Enum):
    """Tipos de ação suportados."""
    RUN_FUNCTION = "run_function"
    RUN_SHELL = "run_shell"
    RUN_TESTS = "run_tests"
    READ_FILE = "read_file"
    EDIT_FILE = "edit_file"
    BROWSE = "browse"
    SEARCH_CODE = "search_code"
    CREATE_PIPELINE = "create_pipeline"
    RUN_PIPELINE = "run_pipeline"
    CREATE_ADAPTER = "create_adapter"
    FINISH = "finish"


class TaskSource(str, Enum):
    """Origem da tarefa."""
    USER_REQUEST = "user_request"
    SELF_HEALING = "self_healing"
    AUTO_EVOLUTION = "auto_evolution"
    PROACTIVE = "proactive"


class TaskPriority(str, Enum):
    """Prioridade da tarefa."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class AgentAction:
    """Ação decidida pelo LLM."""
    action_type: ActionType
    parameters: Dict[str, Any]
    reasoning: str = ""
    step_number: int = 0
    
    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,            "parameters": self.parameters,
            "reasoning": self.reasoning,
            "step_number": self.step_number,
        }
    
    @classmethod
    def from_dict(cls,  dict) -> "AgentAction":
        return cls(
            action_type=ActionType(data.get("action_type", "finish")),
            parameters=data.get("parameters", {}),
            reasoning=data.get("reasoning", ""),
            step_number=data.get("step_number", 0),
        )


@dataclass
class AgentObservation:
    """Resultado da execução."""
    action: AgentAction
    output: str = ""
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "action": self.action.to_dict(),
            "output": self.output,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class AgentTask:
    """Tarefa para o agente."""
    task_id: str
    source: TaskSource
    priority: TaskPriority
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    success_criteria: str = ""
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "source": self.source.value,
            "priority": self.priority.value,
            "description": self.description,
            "context": self.context,            "constraints": self.constraints,
            "success_criteria": self.success_criteria,
        }