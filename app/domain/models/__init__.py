# -*- coding: utf-8 -*-
"""Domain models
CORREÇÃO: Exportação correta de InteractionStatus e ThoughtLog.
"""
from .command import Command, CommandType, Intent, Response
from .device import Capability, CommandResult, Device
from .evolution_reward import EvolutionReward
from .mission import Mission, MissionResult
from .thought_log import InteractionStatus, ThoughtLog
from .capability import JarvisCapability
from .soldier import (
    SoldierStatus,
    SoldierRegistration,
    SoldierRecord,
    LocationPayload,
    NearbyDevice,
    SystemState,
    TelemetryPayload,
)
from .viability import (
    RiskLevel,
    ImpactLevel,
    CostEstimate,
    ImpactEstimate,
    RiskEstimate,
    ViabilityMatrix,
)
from .agent import ActionType, TaskSource, TaskPriority, AgentAction, AgentObservation, AgentTask
from .system_state import SystemStatus

__all__ = [
    # Command models
    "Command",
    "CommandType",
    "Intent",
    "Response",
    
    # Device models
    "Device",
    "Capability",
    "CommandResult",
    
    # Evolution models
    "EvolutionReward",
    "Mission",
    "MissionResult",
    
    # Thought log models
    "ThoughtLog",
    "InteractionStatus",
    
    # Capability models
    "JarvisCapability",
    
    # Soldier models
    "SoldierStatus",
    "SoldierRegistration",
    "SoldierRecord",
    "LocationPayload",
    "NearbyDevice",
    "SystemState",
    "TelemetryPayload",
    
    # Viability models
    "RiskLevel",
    "ImpactLevel",
    "CostEstimate",
    "ImpactEstimate",
    "RiskEstimate",
    "ViabilityMatrix",
    
    # Agent models
    "ActionType",
    "TaskSource",
    "TaskPriority",
    "AgentAction",
    "AgentObservation",
    "AgentTask",
    
    # System state
    "SystemStatus",
]