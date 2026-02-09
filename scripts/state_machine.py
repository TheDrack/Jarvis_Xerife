#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Self-Healing State Machine

This module implements the state machine logic for the self-healing system,
following the rules specified in the requirements:

States:
- CHANGE_REQUESTED: Error identified and can be auto-fixed
- NEEDS_HUMAN: Error requires human intervention
- SUCCESS: Fix applied successfully
- FAILED_LIMIT: Maximum repair attempts reached

Error Identification:
- AssertionError, ImportError, NameError, SyntaxError, LogicError -> CHANGE_REQUESTED
- Timeout, ConnectionError, HTTP 429, 500, 503 -> NEEDS_HUMAN (Infrastructure failure)
- Other errors -> NEEDS_HUMAN (Unidentified error)

Repair Cycle:
- Counter starts at 0, limit is 3
- While state is CHANGE_REQUESTED and counter < limit:
  - Generate minimal patch (1 file, 1 fix at a time)
  - Apply patch and run pytest
  - If pytest passes -> SUCCESS
  - If pytest fails -> increment counter
  - If counter == limit -> FAILED_LIMIT
"""

from enum import Enum
from typing import Dict, Optional, Any
import logging
import re

logger = logging.getLogger(__name__)


class State(Enum):
    """State machine states"""
    CHANGE_REQUESTED = "CHANGE_REQUESTED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    SUCCESS = "SUCCESS"
    FAILED_LIMIT = "FAILED_LIMIT"


class FailureReason(Enum):
    """Reasons for NEEDS_HUMAN state"""
    INFRASTRUCTURE_FAILURE = "Falha de Infra"
    UNIDENTIFIED_ERROR = "Erro não identificado"


class SelfHealingStateMachine:
    """
    Self-healing state machine for automated error fixing.
    
    Attributes:
        state: Current state of the machine
        counter: Number of repair attempts
        limit: Maximum number of repair attempts
        failure_reason: Reason for NEEDS_HUMAN state (if applicable)
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
        Initialize the state machine.
        
        Args:
            limit: Maximum number of repair attempts (default: 3)
        """
        self.state = State.CHANGE_REQUESTED
        self.counter = 0
        self.limit = limit
        self.failure_reason: Optional[FailureReason] = None
        self.error_type: Optional[str] = None
        
        logger.info(f"State Machine initialized with limit={limit}")
    
    def identify_error(self, error_message: str, traceback: Optional[str] = None) -> State:
        """
        Identify error type and set the appropriate state.
        
        Args:
            error_message: The error message
            traceback: Optional traceback information
            
        Returns:
            The new state
        """
        # Combine error message and traceback for analysis
        full_error = f"{error_message}\n{traceback or ''}"
        
        # Reset state-specific fields before classification
        self.failure_reason = None
        self.error_type = None
        
        # Check for auto-fixable errors
        for error_type in self.AUTO_FIXABLE_ERRORS:
            if re.search(error_type, full_error, re.IGNORECASE):
                self.state = State.CHANGE_REQUESTED
                self.error_type = error_type
                logger.info(f"✓ Error identified: {error_type} -> State: CHANGE_REQUESTED")
                return self.state
        
        # Check for infrastructure errors
        for error_pattern in self.INFRASTRUCTURE_ERRORS:
            if re.search(error_pattern, full_error, re.IGNORECASE):
                self.state = State.NEEDS_HUMAN
                self.failure_reason = FailureReason.INFRASTRUCTURE_FAILURE
                self.error_type = error_pattern
                logger.warning(f"⚠ Infrastructure error detected: {error_pattern} -> State: NEEDS_HUMAN (Falha de Infra)")
                return self.state
        
        # Unknown error type
        self.state = State.NEEDS_HUMAN
        self.failure_reason = FailureReason.UNIDENTIFIED_ERROR
        logger.warning(f"⚠ Unidentified error -> State: NEEDS_HUMAN (Erro não identificado)")
        return self.state
    
    def can_attempt_repair(self) -> bool:
        """
        Check if we can attempt a repair.
        
        Returns:
            True if state is CHANGE_REQUESTED and counter < limit
        """
        can_repair = (self.state == State.CHANGE_REQUESTED and self.counter < self.limit)
        
        if not can_repair:
            if self.state != State.CHANGE_REQUESTED:
                logger.info(f"Cannot attempt repair: state is {self.state.value}")
            elif self.counter >= self.limit:
                logger.info(f"Cannot attempt repair: counter ({self.counter}) reached limit ({self.limit})")
        
        return can_repair
    
    def record_repair_attempt(self, success: bool) -> State:
        """
        Record a repair attempt and update state.
        
        Args:
            success: Whether the repair was successful (pytest passed)
            
        Returns:
            The new state
        """
        self.counter += 1
        logger.info(f"Repair attempt {self.counter}/{self.limit}")
        
        if success:
            self.state = State.SUCCESS
            logger.info(f"✅ Repair successful -> State: SUCCESS")
            return self.state
        
        # Repair failed
        if self.counter >= self.limit:
            self.state = State.FAILED_LIMIT
            logger.warning(f"❌ Repair limit reached -> State: FAILED_LIMIT")
        else:
            logger.info(f"Repair failed, will retry (attempt {self.counter}/{self.limit})")
        
        return self.state
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the state machine.
        
        Returns:
            Dictionary with current state information
        """
        return {
            "state": self.state.value,
            "counter": self.counter,
            "limit": self.limit,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "error_type": self.error_type,
            "can_repair": self.can_attempt_repair(),
        }
    
    def should_notify_human(self) -> bool:
        """
        Check if human notification is needed.
        
        Returns:
            True if state is NEEDS_HUMAN or FAILED_LIMIT
        """
        return self.state in [State.NEEDS_HUMAN, State.FAILED_LIMIT]
    
    def get_final_message(self) -> str:
        """
        Get a human-readable final message based on current state.
        
        Returns:
            Formatted message describing the final state
        """
        if self.state == State.SUCCESS:
            return f"✅ Auto-reparo concluído com sucesso após {self.counter} tentativa(s)"
        
        elif self.state == State.FAILED_LIMIT:
            return (
                f"❌ Limite de tentativas atingido ({self.limit}).\n"
                f"   Intervenção manual necessária.\n"
                f"   Tipo de erro: {self.error_type or 'Desconhecido'}"
            )
        
        elif self.state == State.NEEDS_HUMAN:
            reason = self.failure_reason.value if self.failure_reason else "Desconhecido"
            return (
                f"⚠ Intervenção humana necessária.\n"
                f"   Motivo: {reason}\n"
                f"   Tipo de erro: {self.error_type or 'Desconhecido'}"
            )
        
        else:  # CHANGE_REQUESTED
            return f"🔧 Aguardando tentativa de reparo ({self.counter}/{self.limit})"
