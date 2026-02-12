#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Metabolism State Machine - Jarvis DNA Mutation Control

This module implements the metabolic state machine for the Jarvis Metabolism Flow,
treating the repository as DNA and changes as controlled mutations.

Metabolic States:
- METABOLISM_ACTIVE: Mutation can be attempted (homeostasis maintained)
- COMMANDER_NEEDED: Requires human consciousness (escalation)
- HOMEOSTASIS_ACHIEVED: Mutation successful (DNA stable)
- METABOLIC_LIMIT: Maximum mutation cycles reached (3 cycles)

Legacy States (for backward compatibility):
- CHANGE_REQUESTED: Error identified and can be auto-fixed
- NEEDS_HUMAN: Error requires human intervention
- SUCCESS: Fix applied successfully
- FAILED_LIMIT: Maximum repair attempts reached

Mutation Classification:
- Auto-fixable (AssertionError, ImportError, NameError, SyntaxError, etc.) -> METABOLISM_ACTIVE
- Infrastructure errors (Timeout, ConnectionError, HTTP 429/500/503) -> COMMANDER_NEEDED
- Unidentified errors -> COMMANDER_NEEDED

Metabolic Cycle (max 3 cycles):
- Counter starts at 0, limit is 3
- While state is METABOLISM_ACTIVE and counter < limit:
  - Mecânico Revisionador analyzes DNA impact
  - Mecânico Consertador applies minimal mutation
  - Vistoria runs pytest (system imunológico)
  - If pytest passes -> HOMEOSTASIS_ACHIEVED
  - If pytest fails -> increment counter
  - If counter == limit -> METABOLIC_LIMIT -> Escalate to COMMANDER

Principles:
- DNA is sacred (all mutations must be understood)
- Tests are the immune system (homeostasis validation)
- Automate without losing consciousness (human has final word)
"""

from enum import Enum
from typing import Dict, Optional, Any
import logging
import re

logger = logging.getLogger(__name__)


class State(Enum):
    """Metabolic state machine states"""
    # New Metabolism States
    METABOLISM_ACTIVE = "METABOLISM_ACTIVE"         # Mutation can proceed
    COMMANDER_NEEDED = "COMMANDER_NEEDED"           # Human intervention required
    HOMEOSTASIS_ACHIEVED = "HOMEOSTASIS_ACHIEVED"   # Mutation successful, DNA stable
    METABOLIC_LIMIT = "METABOLIC_LIMIT"             # 3 cycles reached, escalate
    
    # Legacy States (for backward compatibility)
    CHANGE_REQUESTED = "CHANGE_REQUESTED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    SUCCESS = "SUCCESS"
    FAILED_LIMIT = "FAILED_LIMIT"


class FailureReason(Enum):
    """Reasons for COMMANDER_NEEDED / NEEDS_HUMAN state"""
    INFRASTRUCTURE_FAILURE = "Falha de Infra"
    UNIDENTIFIED_ERROR = "Erro não identificado"
    BUSINESS_DECISION = "Decisão de negócio necessária"
    ARCHITECTURAL_JUDGMENT = "Julgamento arquitetural necessário"
    BROAD_IMPACT = "Impacto amplo ou irreversível"


class MutationType(Enum):
    """Types of DNA mutations"""
    CORRECTION = "correção"        # Bug fixes
    CREATION = "criação"           # New features
    MODIFICATION = "modificação"   # Modify existing features
    OPTIMIZATION = "otimização"    # Performance/security improvements
    OPERATIONAL = "operacional"    # Operational actions


class MetabolismStateMachine:
    """
    Metabolism state machine for controlled DNA mutations.
    
    Treats the repository as DNA and manages mutation cycles with homeostasis validation.
    
    Attributes:
        state: Current metabolic state
        counter: Number of metabolic cycles (max 3)
        limit: Maximum number of metabolic cycles
        escalation_reason: Reason for COMMANDER_NEEDED state (if applicable)
        mutation_type: Type of DNA mutation being attempted
    """
    
    # Error patterns that can be auto-fixed
    AUTO_FIXABLE_ERRORS = [
        'AssertionError',
        'ImportError',
        'NameError',
        'SyntaxError',
        'LogicError',
    ]
    
    # Infrastructure error patterns that need human intervention
    INFRASTRUCTURE_ERRORS = [
        'Timeout',
        'TimeoutError',
        'ConnectionError',
        'ConnectTimeout',
        'ReadTimeout',
        'HTTPError.*429',  # HTTP 429 Too Many Requests
        'HTTPError.*500',  # HTTP 500 Internal Server Error
        'HTTPError.*503',  # HTTP 503 Service Unavailable
        'HTTP 429',
        'HTTP 500',
        'HTTP 503',
    ]
    
    def __init__(self, limit: int = 3):
        """
        Initialize the metabolic state machine.
        
        Args:
            limit: Maximum number of metabolic cycles (default: 3)
        """
        self.state = State.METABOLISM_ACTIVE
        self.counter = 0
        self.limit = limit
        self.escalation_reason: Optional[FailureReason] = None
        self.mutation_type: Optional[MutationType] = None
        self.error_type: Optional[str] = None
        
        logger.info(f"🧬 Metabolism State Machine initialized - Max cycles: {limit}")
    
    def identify_error(self, error_message: str, traceback: Optional[str] = None) -> State:
        """
        Identify error type and set the appropriate metabolic state.
        
        Args:
            error_message: The error message
            traceback: Optional traceback information
            
        Returns:
            The new metabolic state (or legacy equivalent for backward compatibility)
        """
        # Combine error message and traceback for analysis
        full_error = f"{error_message}\n{traceback or ''}"
        
        # Reset state-specific fields before classification
        self.escalation_reason = None
        self.error_type = None
        self.mutation_type = MutationType.CORRECTION
        
        # Check for auto-fixable errors (DNA mutations we can handle)
        for error_type in self.AUTO_FIXABLE_ERRORS:
            if re.search(error_type, full_error, re.IGNORECASE):
                # Use legacy state for backward compatibility
                self.state = State.CHANGE_REQUESTED
                self.error_type = error_type
                logger.info(f"✓ DNA mutation identified: {error_type} -> State: CHANGE_REQUESTED")
                return self.state
        
        # Check for infrastructure errors (requires COMMANDER)
        for error_pattern in self.INFRASTRUCTURE_ERRORS:
            if re.search(error_pattern, full_error, re.IGNORECASE):
                # Use legacy state for backward compatibility
                self.state = State.NEEDS_HUMAN
                self.escalation_reason = FailureReason.INFRASTRUCTURE_FAILURE
                self.error_type = error_pattern
                logger.warning(f"⚠ Infrastructure error detected: {error_pattern} -> State: NEEDS_HUMAN (Falha de Infra)")
                return self.state
        
        # Unknown error type (requires COMMANDER review)
        # Use legacy state for backward compatibility
        self.state = State.NEEDS_HUMAN
        self.escalation_reason = FailureReason.UNIDENTIFIED_ERROR
        logger.warning(f"⚠ Unidentified error -> State: NEEDS_HUMAN (Erro não identificado)")
        return self.state
    
    def can_attempt_mutation(self) -> bool:
        """
        Check if we can attempt a DNA mutation.
        
        Returns:
            True if state allows mutations and counter < limit
        """
        # Accept both new and legacy states for backward compatibility
        can_mutate = (
            self.state in [State.METABOLISM_ACTIVE, State.CHANGE_REQUESTED] and 
            self.counter < self.limit
        )
        
        if not can_mutate:
            if self.state not in [State.METABOLISM_ACTIVE, State.CHANGE_REQUESTED]:
                logger.info(f"🛑 Cannot attempt mutation: state is {self.state.value}")
            elif self.counter >= self.limit:
                logger.info(f"🛑 Cannot attempt mutation: cycle counter ({self.counter}) reached limit ({self.limit})")
        
        return can_mutate
    
    def can_attempt_repair(self) -> bool:
        """
        Legacy method for backward compatibility.
        
        Returns:
            True if state allows mutation attempts
        """
        return self.can_attempt_mutation()
    
    def record_metabolic_cycle(self, homeostasis_ok: bool) -> State:
        """
        Record a metabolic cycle and update state.
        
        A metabolic cycle includes: Analysis → Mutation → Homeostasis Validation (pytest)
        
        Args:
            homeostasis_ok: Whether homeostasis was maintained (pytest passed)
            
        Returns:
            The new metabolic state (or legacy equivalent for backward compatibility)
        """
        self.counter += 1
        logger.info(f"🔁 Metabolic cycle {self.counter}/{self.limit} completed")
        
        if homeostasis_ok:
            # Use legacy state for backward compatibility
            self.state = State.SUCCESS
            logger.info(f"✅ Homeostasis achieved - DNA is stable -> State: SUCCESS")
            return self.state
        
        # Homeostasis not maintained (tests failed)
        if self.counter >= self.limit:
            # Use legacy state for backward compatibility
            self.state = State.FAILED_LIMIT
            logger.warning(f"⚠️ Metabolic limit reached ({self.limit} cycles) -> State: FAILED_LIMIT")
            logger.warning(f"🚨 Escalating to COMMANDER (human intervention required)")
        else:
            # Stay in CHANGE_REQUESTED for next cycle attempt
            self.state = State.CHANGE_REQUESTED
            logger.info(f"❌ Homeostasis not achieved, will retry (cycle {self.counter}/{self.limit})")
        
        return self.state
    
    def record_repair_attempt(self, success: bool) -> State:
        """
        Legacy method for backward compatibility.
        
        Args:
            success: Whether the repair was successful (pytest passed)
            
        Returns:
            The new state
        """
        return self.record_metabolic_cycle(homeostasis_ok=success)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current metabolic status.
        
        Returns:
            Dictionary with current state information
        """
        return {
            "state": self.state.value,
            "metabolic_cycles": self.counter,
            "cycle_limit": self.limit,
            "escalation_reason": self.escalation_reason.value if self.escalation_reason else None,
            "mutation_type": self.mutation_type.value if self.mutation_type else None,
            "error_type": self.error_type,
            "can_mutate": self.can_attempt_mutation(),
            # Legacy fields
            "counter": self.counter,
            "limit": self.limit,
            "failure_reason": self.escalation_reason.value if self.escalation_reason else None,
            "can_repair": self.can_attempt_mutation(),
        }
    
    def should_escalate_to_commander(self) -> bool:
        """
        Check if escalation to COMMANDER (human) is needed.
        
        Returns:
            True if state requires human intervention
        """
        return self.state in [
            State.COMMANDER_NEEDED, 
            State.METABOLIC_LIMIT,
            # Legacy states
            State.NEEDS_HUMAN,
            State.FAILED_LIMIT
        ]
    
    def should_notify_human(self) -> bool:
        """
        Legacy method for backward compatibility.
        
        Returns:
            True if human intervention is needed
        """
        return self.should_escalate_to_commander()
    
    @property
    def failure_reason(self) -> Optional[FailureReason]:
        """
        Legacy property for backward compatibility.
        Maps escalation_reason to failure_reason.
        """
        return self.escalation_reason
    
    @failure_reason.setter
    def failure_reason(self, value: Optional[FailureReason]):
        """
        Legacy property setter for backward compatibility.
        """
        self.escalation_reason = value
    
    def get_final_message(self) -> str:
        """
        Get a human-readable final message based on current metabolic state.
        
        Returns:
            Formatted message describing the final state
        """
        if self.state == State.HOMEOSTASIS_ACHIEVED:
            return f"✅ Homeostase alcançada após {self.counter} ciclo(s) metabólico(s) - DNA estável"
        
        elif self.state == State.METABOLIC_LIMIT:
            return (
                f"🚨 Limite metabólico atingido ({self.limit} ciclos).\n"
                f"   COMANDANTE (humano) deve intervir.\n"
                f"   Tipo de mutação: {self.error_type or 'Desconhecido'}\n"
                f"   Princípio: Nenhuma alteração no DNA sem compreensão explícita"
            )
        
        elif self.state == State.COMMANDER_NEEDED:
            reason = self.escalation_reason.value if self.escalation_reason else "Desconhecido"
            return (
                f"🎯 COMANDANTE necessário - Consciência superior requerida.\n"
                f"   Motivo: {reason}\n"
                f"   Tipo de erro: {self.error_type or 'Desconhecido'}\n"
                f"   Princípio: O humano sempre tem a palavra final"
            )
        
        elif self.state == State.METABOLISM_ACTIVE:
            return f"🧬 Metabolismo ativo - Aguardando ciclo {self.counter + 1}/{self.limit}"
        
        # Legacy states
        elif self.state == State.SUCCESS:
            return f"✅ Auto-reparo concluído com sucesso após {self.counter} tentativa(s)"
        
        elif self.state == State.FAILED_LIMIT:
            return (
                f"❌ Limite de tentativas atingido ({self.limit}).\n"
                f"   Intervenção manual necessária.\n"
                f"   Tipo de erro: {self.error_type or 'Desconhecido'}"
            )
        
        elif self.state == State.NEEDS_HUMAN:
            reason = self.escalation_reason.value if self.escalation_reason else "Desconhecido"
            return (
                f"⚠ Intervenção humana necessária.\n"
                f"   Motivo: {reason}\n"
                f"   Tipo de erro: {self.error_type or 'Desconhecido'}"
            )
        
        else:  # CHANGE_REQUESTED
            return f"🔧 Aguardando tentativa de reparo ({self.counter}/{self.limit})"


# Legacy compatibility alias
SelfHealingStateMachine = MetabolismStateMachine
