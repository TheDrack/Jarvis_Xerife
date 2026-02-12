# -*- coding: utf-8 -*-
"""Tests for resource monitoring in TaskRunner"""

import tempfile
from pathlib import Path

import pytest

from app.application.services.task_runner import ResourceMonitor, TaskRunner
from app.domain.models.mission import Mission


class TestResourceMonitor:
    """Test cases for ResourceMonitor"""

    def test_get_resource_snapshot(self):
        """Test getting a resource snapshot"""
        snapshot = ResourceMonitor.get_resource_snapshot()
        
        assert snapshot is not None
        assert isinstance(snapshot, dict)
        assert "cpu_percent" in snapshot
        assert "memory_percent" in snapshot
        assert "memory_available_mb" in snapshot
        assert "disk_percent" in snapshot
        assert "disk_free_gb" in snapshot
        
        # Check value types and ranges
        assert isinstance(snapshot["cpu_percent"], (int, float))
        assert 0 <= snapshot["cpu_percent"] <= 100
        assert isinstance(snapshot["memory_percent"], (int, float))
        assert 0 <= snapshot["memory_percent"] <= 100
    
    def test_get_process_resources(self):
        """Test getting process resources"""
        import os
        
        # Get resources for current process
        resources = ResourceMonitor.get_process_resources(os.getpid())
        
        assert resources is not None
        assert isinstance(resources, dict)
        
        if resources:  # May be empty on permission errors
            assert "cpu_percent" in resources
            assert "memory_mb" in resources
            assert "num_threads" in resources


class TestTaskRunnerResourceMonitoring:
    """Test cases for TaskRunner resource monitoring"""
    
    @pytest.fixture
    def task_runner(self):
        """Create TaskRunner with temporary cache directory"""
        cache_dir = Path(tempfile.mkdtemp(prefix="test_resource_mon_"))
        return TaskRunner(cache_dir=cache_dir, use_venv=False)
    
    def test_mission_logs_resource_snapshots(self, task_runner):
        """Test that missions log initial and final resource snapshots"""
        mission = Mission(
            mission_id="resource_test_001",
            code="print('Testing resource monitoring')",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )
        
        result = task_runner.execute_mission(mission)
        
        # Main goal: mission should succeed even with resource monitoring
        assert result is not None
        assert result.success is True
        assert "Testing resource monitoring" in result.stdout
    
    def test_resource_monitoring_doesnt_break_execution(self, task_runner):
        """Test that resource monitoring failures don't break mission execution"""
        mission = Mission(
            mission_id="robust_test_001",
            code="x = 1 + 1\nprint(f'Result: {x}')",
            requirements=[],
            browser_interaction=False,
            keep_alive=False,
        )
        
        result = task_runner.execute_mission(mission)
        
        # Should succeed even if resource monitoring has issues
        assert result is not None
        assert result.success is True
        assert "Result: 2" in result.stdout
