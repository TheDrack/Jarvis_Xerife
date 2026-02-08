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
