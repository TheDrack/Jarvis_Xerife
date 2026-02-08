# -*- coding: utf-8 -*-
"""Tests for TaskRunner - Ephemeral script execution service"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.application.services.task_runner import TaskRunner
from app.domain.models.mission import Mission, MissionResult


class TestTaskRunner:
    """Test cases for TaskRunner"""

    @pytest.fixture
    def task_runner(self):
        """Create TaskRunner with temporary cache directory"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_task_runner_"))
        return TaskRunner(cache_dir=cache_dir, use_venv=False)

    def test_task_runner_initialization(self, task_runner):
        """Test that TaskRunner initializes correctly"""
        assert task_runner is not None
        assert task_runner.cache_dir.exists()
        assert task_runner.use_venv is False

    def test_execute_simple_mission(self, task_runner):
        """Test executing a simple mission without dependencies"""
        mission = Mission(
            mission_id="test_001",
            code="print('Hello, World!')",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert isinstance(result, MissionResult)
        assert result.mission_id == "test_001"
        assert result.success is True
        assert "Hello, World!" in result.stdout
        assert result.exit_code == 0

    def test_execute_mission_with_error(self, task_runner):
        """Test executing a mission that raises an error"""
        mission = Mission(
            mission_id="test_002",
            code="raise ValueError('Test error')",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert result.success is False
        assert result.exit_code == 1
        assert "ValueError" in result.stderr or "Test error" in result.stderr

    def test_execute_mission_with_variables(self, task_runner):
        """Test executing a mission that uses variables"""
        mission = Mission(
            mission_id="test_003",
            code="""
x = 10
y = 20
print(f"Sum: {x + y}")
""",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert result.success is True
        assert "Sum: 30" in result.stdout

    def test_execute_mission_with_stderr(self, task_runner):
        """Test capturing stderr from a mission"""
        mission = Mission(
            mission_id="test_004",
            code="""
import sys
print("stdout message")
print("stderr message", file=sys.stderr)
""",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert result.success is True
        assert "stdout message" in result.stdout
        assert "stderr message" in result.stderr

    def test_execute_mission_timeout(self, task_runner):
        """Test mission execution timeout"""
        mission = Mission(
            mission_id="test_005",
            code="""
import time
time.sleep(10)
print("This should not execute")
""",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
            timeout=1,  # 1 second timeout
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert result.success is False
        assert result.exit_code == 124  # Timeout exit code

    def test_mission_result_metadata(self, task_runner):
        """Test that mission result includes metadata"""
        mission = Mission(
            mission_id="test_006",
            code="print('test')",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert result.metadata is not None
        assert "script_path" in result.metadata
        assert "persistent" in result.metadata
        assert result.metadata["persistent"] is False

    def test_mission_with_keep_alive(self, task_runner):
        """Test mission with keep_alive flag"""
        mission = Mission(
            mission_id="test_007",
            code="print('persistent mission')",
            requirements=[],
            browser_interaction=False,
            keep_alive=True,
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert result.success is True
        assert result.metadata["persistent"] is True

    def test_execution_time_tracking(self, task_runner):
        """Test that execution time is tracked"""
        mission = Mission(
            mission_id="test_008",
            code="""
import time
time.sleep(0.1)
print('done')
""",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )

        result = task_runner.execute_mission(mission)

        assert result is not None
        assert result.success is True
        assert result.execution_time > 0
        assert result.execution_time >= 0.1

    def test_mission_to_dict(self):
        """Test Mission to_dict conversion"""
        mission = Mission(
            mission_id="test_dict",
            code="print('test')",
            requirements=["requests"],
            browser_interaction=True,
            keep_alive=False,
            timeout=120,
            metadata={"key": "value"},
        )

        mission_dict = mission.to_dict()

        assert mission_dict["mission_id"] == "test_dict"
        assert mission_dict["code"] == "print('test')"
        assert mission_dict["requirements"] == ["requests"]
        assert mission_dict["browser_interaction"] is True
        assert mission_dict["keep_alive"] is False
        assert mission_dict["timeout"] == 120
        assert mission_dict["metadata"] == {"key": "value"}

    def test_mission_from_dict(self):
        """Test Mission from_dict conversion"""
        data = {
            "mission_id": "test_from_dict",
            "code": "print('hello')",
            "requirements": ["numpy"],
            "browser_interaction": False,
            "keep_alive": True,
            "timeout": 60,
            "metadata": {"test": "data"},
        }

        mission = Mission.from_dict(data)

        assert mission.mission_id == "test_from_dict"
        assert mission.code == "print('hello')"
        assert mission.requirements == ["numpy"]
        assert mission.browser_interaction is False
        assert mission.keep_alive is True
        assert mission.timeout == 60
        assert mission.metadata == {"test": "data"}

    def test_mission_result_to_dict(self):
        """Test MissionResult to_dict conversion"""
        result = MissionResult(
            mission_id="test_result",
            success=True,
            stdout="output",
            stderr="",
            exit_code=0,
            execution_time=1.5,
            error=None,
            metadata={"key": "value"},
        )

        result_dict = result.to_dict()

        assert result_dict["mission_id"] == "test_result"
        assert result_dict["success"] is True
        assert result_dict["stdout"] == "output"
        assert result_dict["stderr"] == ""
        assert result_dict["exit_code"] == 0
        assert result_dict["execution_time"] == 1.5
        assert result_dict["error"] is None
        assert result_dict["metadata"] == {"key": "value"}

    def test_task_runner_with_sandbox_mode(self):
        """Test TaskRunner initialization with sandbox mode"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_sandbox_"))
        runner = TaskRunner(
            cache_dir=cache_dir,
            use_venv=False,
            sandbox_mode=True,
        )
        
        assert runner.sandbox_mode is True
        assert runner.sandbox_dir.exists()
        assert "sandbox" in str(runner.sandbox_dir)

    def test_task_runner_with_budget_cap(self):
        """Test TaskRunner initialization with budget cap"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_budget_"))
        runner = TaskRunner(
            cache_dir=cache_dir,
            use_venv=False,
            budget_cap_usd=50.0,
        )
        
        assert runner.budget_cap_usd == 50.0
        assert runner.total_cost_usd == 0.0
        assert runner.is_within_budget() is True

    def test_track_mission_cost(self):
        """Test mission cost tracking"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_cost_"))
        runner = TaskRunner(cache_dir=cache_dir, use_venv=False, budget_cap_usd=10.0)
        
        # Track some costs
        runner.track_mission_cost("mission_1", 2.5)
        runner.track_mission_cost("mission_2", 3.0)
        runner.track_mission_cost("mission_1", 1.5)  # Additional cost for mission_1
        
        # Check totals
        assert runner.get_mission_cost("mission_1") == 4.0
        assert runner.get_mission_cost("mission_2") == 3.0
        assert runner.get_total_cost() == 7.0
        assert runner.is_within_budget() is True

    def test_budget_exceeded(self):
        """Test budget cap enforcement"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_budget_exceed_"))
        runner = TaskRunner(cache_dir=cache_dir, use_venv=False, budget_cap_usd=5.0)
        
        # Track costs that exceed budget
        runner.track_mission_cost("mission_1", 3.0)
        runner.track_mission_cost("mission_2", 4.0)
        
        # Should exceed budget
        assert runner.get_total_cost() == 7.0
        assert runner.is_within_budget() is False

    def test_budget_status(self):
        """Test budget status reporting"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_status_"))
        runner = TaskRunner(cache_dir=cache_dir, use_venv=False, budget_cap_usd=100.0)
        
        runner.track_mission_cost("mission_1", 25.0)
        runner.track_mission_cost("mission_2", 35.0)
        
        status = runner.get_budget_status()
        
        assert status["total_cost_usd"] == 60.0
        assert status["budget_cap_usd"] == 100.0
        assert status["remaining_usd"] == 40.0
        assert status["within_budget"] is True
        assert status["missions_tracked"] == 2

    def test_budget_status_no_cap(self):
        """Test budget status when no cap is set"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_no_cap_"))
        runner = TaskRunner(cache_dir=cache_dir, use_venv=False)
        
        runner.track_mission_cost("mission_1", 100.0)
        
        status = runner.get_budget_status()
        
        assert status["total_cost_usd"] == 100.0
        assert status["budget_cap_usd"] is None
        assert status["remaining_usd"] is None
        assert status["within_budget"] is True
