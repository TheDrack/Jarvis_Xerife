from app.core.nexuscomponent import NexusComponent
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for Self-Healing State Machine

These tests validate the state machine logic for error identification
and repair cycle management.
"""

import pytest
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from state_machine import SelfHealingStateMachine, State, FailureReason


class TestErrorIdentification(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test error identification logic"""
    
    def test_assertion_error_triggers_change_requested(self):
        """AssertionError should trigger CHANGE_REQUESTED state"""
        machine = SelfHealingStateMachine()
        error = "AssertionError: Expected 5 but got 3"
        
        state = machine.identify_error(error)
        
        assert state == State.CHANGE_REQUESTED
        assert machine.error_type == 'AssertionError'
    
    def test_import_error_triggers_change_requested(self):
        """ImportError should trigger CHANGE_REQUESTED state"""
        machine = SelfHealingStateMachine()
        error = "ImportError: cannot import name 'foo' from 'bar'"
        
        state = machine.identify_error(error)
        
        assert state == State.CHANGE_REQUESTED
        assert machine.error_type == 'ImportError'
    
    def test_name_error_triggers_change_requested(self):
        """NameError should trigger CHANGE_REQUESTED state"""
        machine = SelfHealingStateMachine()
        error = "NameError: name 'undefined_var' is not defined"
        
        state = machine.identify_error(error)
        
        assert state == State.CHANGE_REQUESTED
        assert machine.error_type == 'NameError'
    
    def test_syntax_error_triggers_change_requested(self):
        """SyntaxError should trigger CHANGE_REQUESTED state"""
        machine = SelfHealingStateMachine()
        error = "SyntaxError: invalid syntax"
        
        state = machine.identify_error(error)
        
        assert state == State.CHANGE_REQUESTED
        assert machine.error_type == 'SyntaxError'
    
    def test_logic_error_triggers_change_requested(self):
        """LogicError should trigger CHANGE_REQUESTED state"""
        machine = SelfHealingStateMachine()
        error = "LogicError: Invalid operation"
        
        state = machine.identify_error(error)
        
        assert state == State.CHANGE_REQUESTED
        assert machine.error_type == 'LogicError'
    
    def test_timeout_triggers_needs_human(self):
        """Timeout should trigger NEEDS_HUMAN state with infrastructure reason"""
        machine = SelfHealingStateMachine()
        error = "TimeoutError: Connection timed out"
        
        state = machine.identify_error(error)
        
        assert state == State.NEEDS_HUMAN
        assert machine.failure_reason == FailureReason.INFRASTRUCTURE_FAILURE
    
    def test_connection_error_triggers_needs_human(self):
        """ConnectionError should trigger NEEDS_HUMAN state"""
        machine = SelfHealingStateMachine()
        error = "ConnectionError: Failed to connect to server"
        
        state = machine.identify_error(error)
        
        assert state == State.NEEDS_HUMAN
        assert machine.failure_reason == FailureReason.INFRASTRUCTURE_FAILURE
    
    def test_http_429_triggers_needs_human(self):
        """HTTP 429 should trigger NEEDS_HUMAN state"""
        machine = SelfHealingStateMachine()
        error = "HTTPError: 429 Too Many Requests"
        
        state = machine.identify_error(error)
        
        assert state == State.NEEDS_HUMAN
        assert machine.failure_reason == FailureReason.INFRASTRUCTURE_FAILURE
    
    def test_http_500_triggers_needs_human(self):
        """HTTP 500 should trigger NEEDS_HUMAN state"""
        machine = SelfHealingStateMachine()
        error = "HTTPError: 500 Internal Server Error"
        
        state = machine.identify_error(error)
        
        assert state == State.NEEDS_HUMAN
        assert machine.failure_reason == FailureReason.INFRASTRUCTURE_FAILURE
    
    def test_http_503_triggers_needs_human(self):
        """HTTP 503 should trigger NEEDS_HUMAN state"""
        machine = SelfHealingStateMachine()
        error = "HTTPError: 503 Service Unavailable"
        
        state = machine.identify_error(error)
        
        assert state == State.NEEDS_HUMAN
        assert machine.failure_reason == FailureReason.INFRASTRUCTURE_FAILURE
    
    def test_unknown_error_triggers_needs_human(self):
        """Unknown error should trigger NEEDS_HUMAN state"""
        machine = SelfHealingStateMachine()
        error = "SomeWeirdError: This is not a known error type"
        
        state = machine.identify_error(error)
        
        assert state == State.NEEDS_HUMAN
        assert machine.failure_reason == FailureReason.UNIDENTIFIED_ERROR


class TestRepairCycle(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test repair cycle logic"""
    
    def test_initial_counter_is_zero(self):
        """Counter should start at 0"""
        machine = SelfHealingStateMachine()
        assert machine.counter == 0
    
    def test_default_limit_is_three(self):
        """Default limit should be 3"""
        machine = SelfHealingStateMachine()
        assert machine.limit == 3
    
    def test_custom_limit(self):
        """Should accept custom limit"""
        machine = SelfHealingStateMachine(limit=5)
        assert machine.limit == 5
    
    def test_can_attempt_repair_initial_state(self):
        """Should be able to attempt repair in initial CHANGE_REQUESTED state"""
        machine = SelfHealingStateMachine()
        assert machine.can_attempt_repair() is True
    
    def test_cannot_attempt_repair_needs_human(self):
        """Should not be able to attempt repair in NEEDS_HUMAN state"""
        machine = SelfHealingStateMachine()
        machine.identify_error("TimeoutError: timeout")
        
        assert machine.state == State.NEEDS_HUMAN
        assert machine.can_attempt_repair() is False
    
    def test_successful_repair_sets_success_state(self):
        """Successful repair should set SUCCESS state"""
        machine = SelfHealingStateMachine()
        machine.identify_error("AssertionError: test")
        
        state = machine.record_repair_attempt(success=True)
        
        assert state == State.SUCCESS
        assert machine.counter == 1
    
    def test_failed_repair_increments_counter(self):
        """Failed repair should increment counter"""
        machine = SelfHealingStateMachine()
        machine.identify_error("AssertionError: test")
        
        state = machine.record_repair_attempt(success=False)
        
        assert state == State.CHANGE_REQUESTED
        assert machine.counter == 1
    
    def test_limit_reached_sets_failed_limit_state(self):
        """Reaching limit should set FAILED_LIMIT state"""
        machine = SelfHealingStateMachine(limit=3)
        machine.identify_error("AssertionError: test")
        
        # Fail 3 times
        machine.record_repair_attempt(success=False)
        machine.record_repair_attempt(success=False)
        state = machine.record_repair_attempt(success=False)
        
        assert state == State.FAILED_LIMIT
        assert machine.counter == 3
        assert machine.can_attempt_repair() is False
    
    def test_repair_cycle_workflow(self):
        """Test complete repair cycle workflow"""
        machine = SelfHealingStateMachine(limit=3)
        
        # 1. Identify error
        machine.identify_error("NameError: undefined")
        assert machine.state == State.CHANGE_REQUESTED
        
        # 2. First attempt fails
        assert machine.can_attempt_repair() is True
        machine.record_repair_attempt(success=False)
        assert machine.counter == 1
        assert machine.state == State.CHANGE_REQUESTED
        
        # 3. Second attempt fails
        assert machine.can_attempt_repair() is True
        machine.record_repair_attempt(success=False)
        assert machine.counter == 2
        assert machine.state == State.CHANGE_REQUESTED
        
        # 4. Third attempt succeeds
        assert machine.can_attempt_repair() is True
        machine.record_repair_attempt(success=True)
        assert machine.counter == 3
        assert machine.state == State.SUCCESS


class TestStateStatus(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test state status and reporting"""
    
    def test_get_status_change_requested(self):
        """get_status should return correct info for CHANGE_REQUESTED"""
        machine = SelfHealingStateMachine()
        machine.identify_error("AssertionError: test")
        
        status = machine.get_status()
        
        assert status['state'] == 'CHANGE_REQUESTED'
        assert status['counter'] == 0
        assert status['limit'] == 3
        assert status['error_type'] == 'AssertionError'
        assert status['can_repair'] is True
    
    def test_get_status_needs_human(self):
        """get_status should return correct info for NEEDS_HUMAN"""
        machine = SelfHealingStateMachine()
        machine.identify_error("TimeoutError: timeout")
        
        status = machine.get_status()
        
        assert status['state'] == 'NEEDS_HUMAN'
        assert status['failure_reason'] == 'Falha de Infra'
        assert status['can_repair'] is False
    
    def test_should_notify_human_for_needs_human(self):
        """should_notify_human should return True for NEEDS_HUMAN"""
        machine = SelfHealingStateMachine()
        machine.identify_error("TimeoutError: timeout")
        
        assert machine.should_notify_human() is True
    
    def test_should_notify_human_for_failed_limit(self):
        """should_notify_human should return True for FAILED_LIMIT"""
        machine = SelfHealingStateMachine(limit=1)
        machine.identify_error("AssertionError: test")
        machine.record_repair_attempt(success=False)
        
        assert machine.state == State.FAILED_LIMIT
        assert machine.should_notify_human() is True
    
    def test_should_notify_human_for_success(self):
        """should_notify_human should return False for SUCCESS"""
        machine = SelfHealingStateMachine()
        machine.identify_error("AssertionError: test")
        machine.record_repair_attempt(success=True)
        
        assert machine.state == State.SUCCESS
        assert machine.should_notify_human() is False
    
    def test_get_final_message_success(self):
        """get_final_message should return success message"""
        machine = SelfHealingStateMachine()
        machine.identify_error("AssertionError: test")
        machine.record_repair_attempt(success=True)
        
        message = machine.get_final_message()
        
        assert "sucesso" in message.lower()
        assert "1 tentativa" in message.lower()
    
    def test_get_final_message_failed_limit(self):
        """get_final_message should return failed limit message"""
        machine = SelfHealingStateMachine(limit=3)
        machine.identify_error("AssertionError: test")
        machine.record_repair_attempt(success=False)
        machine.record_repair_attempt(success=False)
        machine.record_repair_attempt(success=False)
        
        message = machine.get_final_message()
        
        assert "limite" in message.lower()
        assert "intervenção manual" in message.lower()
    
    def test_get_final_message_needs_human(self):
        """get_final_message should return needs human message"""
        machine = SelfHealingStateMachine()
        machine.identify_error("TimeoutError: timeout")
        
        message = machine.get_final_message()
        
        assert "intervenção humana" in message.lower()
        assert "falha de infra" in message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
