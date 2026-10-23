"""Shared multi-agent contracts for the Jarvis Harness.

The package is runtime-agnostic: each agent keeps its own model/context while
using the same task and capability contracts.
"""
from .contracts import AgentProfile, TaskSpec, TaskAssignment, TaskStatus
from .scheduler import CostBenefitScheduler, NoEligibleAgentError

__all__ = [
    "AgentProfile",
    "TaskSpec",
    "TaskAssignment",
    "TaskStatus",
    "CostBenefitScheduler",
    "NoEligibleAgentError",
]
