# -*- coding: utf-8 -*-
"""Tests for ThoughtLog model and ThoughtLogService"""

import json
import pytest
from datetime import datetime

from sqlmodel import Session, create_engine, SQLModel

from app.domain.models.thought_log import InteractionStatus, ThoughtLog
from app.application.services.thought_log_service import ThoughtLogService


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing"""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def thought_log_service(engine):
    """Create a ThoughtLogService instance for testing"""
    return ThoughtLogService(engine=engine)


def test_thought_log_model_creation(engine):
    """Test creating a ThoughtLog model instance"""
    thought_log = ThoughtLog(
        mission_id="test_mission_1",
        session_id="session_1",
        status=InteractionStatus.INTERNAL_MONOLOGUE.value,
        thought_process="Analyzing the problem",
        problem_description="CI build failed",
        solution_attempt="Checking logs",
        success=False,
        error_message="Build error",
        retry_count=0,
        context_data=json.dumps({"test": "data"}),
    )
    
    with Session(engine) as session:
        session.add(thought_log)
        session.commit()
        session.refresh(thought_log)
        
        assert thought_log.id is not None
        assert thought_log.mission_id == "test_mission_1"
        assert thought_log.status == InteractionStatus.INTERNAL_MONOLOGUE.value
        assert thought_log.requires_human is False


def test_create_thought(thought_log_service):
    """Test creating a thought log via service"""
    thought = thought_log_service.create_thought(
        mission_id="test_mission_2",
        session_id="session_2",
        thought_process="Testing thought creation",
        problem_description="Test problem",
        solution_attempt="Test solution",
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        success=True,
    )
    
    assert thought is not None
    assert thought.mission_id == "test_mission_2"
    assert thought.success is True
    assert thought.retry_count == 0
    assert thought.requires_human is False


def test_retry_count_increments_on_failure(thought_log_service):
    """Test that retry count increments with each failure"""
    mission_id = "test_mission_3"
    
    # First failure
    thought1 = thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_3",
        thought_process="First attempt",
        problem_description="Problem",
        solution_attempt="Solution 1",
        success=False,
        error_message="Error 1",
    )
    
    assert thought1.retry_count == 0  # First attempt
    
    # Second failure
    thought2 = thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_3",
        thought_process="Second attempt",
        problem_description="Problem",
        solution_attempt="Solution 2",
        success=False,
        error_message="Error 2",
    )
    
    assert thought2.retry_count == 1  # Second attempt
    
    # Third failure
    thought3 = thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_3",
        thought_process="Third attempt",
        problem_description="Problem",
        solution_attempt="Solution 3",
        success=False,
        error_message="Error 3",
    )
    
    assert thought3.retry_count == 2  # Third attempt


def test_escalation_after_max_retries(thought_log_service):
    """Test that mission is escalated to human after 3 failures"""
    mission_id = "test_mission_4"
    
    # Create 3 failures
    for i in range(3):
        thought_log_service.create_thought(
            mission_id=mission_id,
            session_id="session_4",
            thought_process=f"Attempt {i+1}",
            problem_description="Problem",
            solution_attempt=f"Solution {i+1}",
            success=False,
            error_message=f"Error {i+1}",
        )
    
    # Fourth failure should trigger escalation
    thought4 = thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_4",
        thought_process="Fourth attempt",
        problem_description="Problem",
        solution_attempt="Solution 4",
        success=False,
        error_message="Error 4",
    )
    
    assert thought4.requires_human is True
    assert thought4.retry_count == 3
    assert "Auto-correction failed 3 times" in thought4.escalation_reason


def test_get_mission_thoughts(thought_log_service):
    """Test retrieving all thoughts for a mission"""
    mission_id = "test_mission_5"
    
    # Create multiple thoughts
    for i in range(3):
        thought_log_service.create_thought(
            mission_id=mission_id,
            session_id="session_5",
            thought_process=f"Thought {i+1}",
            problem_description="Problem",
            solution_attempt=f"Solution {i+1}",
            success=i == 2,  # Last one succeeds
        )
    
    thoughts = thought_log_service.get_mission_thoughts(mission_id)
    
    assert len(thoughts) == 3
    assert thoughts[0].thought_process == "Thought 1"
    assert thoughts[2].success is True


def test_get_session_thoughts(thought_log_service):
    """Test retrieving all thoughts for a session"""
    session_id = "session_6"
    
    # Create thoughts for different missions in same session
    thought_log_service.create_thought(
        mission_id="mission_a",
        session_id=session_id,
        thought_process="Mission A thought",
        problem_description="Problem A",
        solution_attempt="Solution A",
    )
    
    thought_log_service.create_thought(
        mission_id="mission_b",
        session_id=session_id,
        thought_process="Mission B thought",
        problem_description="Problem B",
        solution_attempt="Solution B",
    )
    
    thoughts = thought_log_service.get_session_thoughts(session_id)
    
    assert len(thoughts) == 2
    assert thoughts[0].mission_id == "mission_a"
    assert thoughts[1].mission_id == "mission_b"


def test_check_requires_human(thought_log_service):
    """Test checking if a mission requires human intervention"""
    mission_id = "test_mission_7"
    
    # Initially no escalation
    assert thought_log_service.check_requires_human(mission_id) is False
    
    # Create 3 failures to trigger escalation
    for i in range(4):
        thought_log_service.create_thought(
            mission_id=mission_id,
            session_id="session_7",
            thought_process=f"Attempt {i+1}",
            problem_description="Problem",
            solution_attempt=f"Solution {i+1}",
            success=False,
            error_message=f"Error {i+1}",
        )
    
    # Now should require human
    assert thought_log_service.check_requires_human(mission_id) is True


def test_generate_consolidated_log(thought_log_service):
    """Test generating consolidated log for a mission"""
    mission_id = "test_mission_8"
    
    # Create a few thoughts
    thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_8",
        thought_process="First thought",
        problem_description="CI failed",
        solution_attempt="Check logs",
        success=False,
        error_message="Build error",
    )
    
    thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_8",
        thought_process="Second thought",
        problem_description="CI failed",
        solution_attempt="Fix dependency",
        success=True,
    )
    
    log = thought_log_service.generate_consolidated_log(mission_id)
    
    assert "test_mission_8" in log
    assert "Total Attempts: 2" in log
    assert "First thought" in log
    assert "Second thought" in log
    assert "SUCCESS" in log
    assert "FAILED" in log


def test_get_pending_escalations(thought_log_service):
    """Test retrieving all pending escalations"""
    # Create a mission that requires escalation
    mission_id = "escalated_mission"
    
    for i in range(4):
        thought_log_service.create_thought(
            mission_id=mission_id,
            session_id="session_9",
            thought_process=f"Attempt {i+1}",
            problem_description="Problem",
            solution_attempt=f"Solution {i+1}",
            success=False,
            error_message=f"Error {i+1}",
        )
    
    escalations = thought_log_service.get_pending_escalations()
    
    assert len(escalations) >= 1
    assert any(e.mission_id == mission_id for e in escalations)
    assert all(e.requires_human for e in escalations)


def test_get_recent_thoughts(thought_log_service):
    """Test retrieving recent thoughts"""
    # Create thoughts with different statuses
    thought_log_service.create_thought(
        mission_id="recent_1",
        session_id="session_10",
        thought_process="Internal thought",
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        problem_description="Problem",
        solution_attempt="Solution",
    )
    
    thought_log_service.create_thought(
        mission_id="recent_2",
        session_id="session_10",
        thought_process="User response",
        status=InteractionStatus.USER_INTERACTION,
        problem_description="Question",
        solution_attempt="Answer",
    )
    
    # Get all recent thoughts
    all_thoughts = thought_log_service.get_recent_thoughts(limit=10)
    assert len(all_thoughts) >= 2
    
    # Get only internal thoughts
    internal_thoughts = thought_log_service.get_recent_thoughts(
        status=InteractionStatus.INTERNAL_MONOLOGUE,
        limit=10
    )
    assert all(t.status == InteractionStatus.INTERNAL_MONOLOGUE.value for t in internal_thoughts)


def test_successful_attempt_resets_retry_count(thought_log_service):
    """Test that successful attempts show retry_count as 0"""
    mission_id = "test_mission_9"
    
    # Create a failure
    thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_11",
        thought_process="Failed attempt",
        problem_description="Problem",
        solution_attempt="Solution",
        success=False,
        error_message="Error",
    )
    
    # Create a success - should have retry_count 0
    thought_success = thought_log_service.create_thought(
        mission_id=mission_id,
        session_id="session_11",
        thought_process="Successful attempt",
        problem_description="Problem",
        solution_attempt="Working solution",
        success=True,
    )
    
    assert thought_success.retry_count == 0
    assert thought_success.requires_human is False
