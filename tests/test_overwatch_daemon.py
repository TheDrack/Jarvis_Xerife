# -*- coding: utf-8 -*-
"""Tests for OverwatchDaemon - Happy Path validation"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.infrastructure.overwatch_adapter import OverwatchDaemon


class TestOverwatchDaemon:
    """Tests for the OverwatchDaemon proactive monitoring background process."""

    @pytest.fixture
    def daemon(self):
        """Create a daemon with very short intervals for testing."""
        d = OverwatchDaemon(
            poll_interval=0.01,
            cpu_threshold=1.0,    # will always trigger in tests if psutil reports anything
            ram_threshold=99.0,   # very high — unlikely to trigger in tests
            inactivity_timeout=9999,  # won't trigger inactivity during tests
        )
        yield d
        d.stop()

    def test_start_and_stop(self, daemon):
        """Daemon should start and stop without error."""
        daemon.start()
        assert daemon._running is True
        time.sleep(0.05)
        daemon.stop()
        assert daemon._running is False

    def test_start_is_idempotent(self, daemon):
        """Calling start() twice should not create two threads."""
        daemon.start()
        thread1 = daemon._thread
        daemon.start()
        assert daemon._thread is thread1
        daemon.stop()

    def test_notify_activity_resets_timer(self, daemon):
        """notify_activity() should reset the inactivity timestamp."""
        old_ts = daemon._last_activity_ts - 100
        daemon._last_activity_ts = old_ts
        daemon.notify_activity()
        assert daemon._last_activity_ts > old_ts

    def test_check_resources_warns_on_high_cpu(self, daemon):
        """High CPU usage should trigger a warning notification."""
        daemon._tick_count = 6  # align with _CPU_CHECK_EVERY
        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.return_value = 99.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=10.0)

        with patch.object(daemon, "_notify") as mock_notify:
            with patch.dict("sys.modules", {"psutil": mock_psutil}):
                daemon._check_resources()

        mock_notify.assert_called_once()
        assert "CPU" in mock_notify.call_args[0][0]

    def test_check_context_file_detects_change(self, daemon, tmp_path):
        """_check_context_file should react when the file mtime changes."""
        ctx_file = tmp_path / "context.json"
        ctx_file.write_text('{"pending_tasks": ["task A"]}')

        import app.adapters.infrastructure.overwatch_adapter as mod
        original = mod._CONTEXT_FILE
        mod._CONTEXT_FILE = ctx_file

        try:
            # First call — just sets baseline
            daemon._check_context_file()
            initial_mtime = daemon._context_mtime

            # Simulate a change by touching the file
            time.sleep(0.05)
            ctx_file.write_text('{"pending_tasks": ["task B"]}')

            with patch.object(daemon, "_on_context_changed") as mock_react:
                daemon._check_context_file()
            mock_react.assert_called_once()
        finally:
            mod._CONTEXT_FILE = original

    def test_get_pending_tasks_from_context(self, daemon, tmp_path):
        """Should parse pending_tasks from a real context.json."""
        ctx_file = tmp_path / "context.json"
        ctx_file.write_text('{"pending_tasks": ["reunião às 15h", "enviar relatório"]}')

        import app.adapters.infrastructure.overwatch_adapter as mod
        original = mod._CONTEXT_FILE
        mod._CONTEXT_FILE = ctx_file
        try:
            tasks = daemon._get_pending_calendar_tasks(limit=5)
            assert "reunião às 15h" in tasks
            assert "enviar relatório" in tasks
        finally:
            mod._CONTEXT_FILE = original

    def test_inactivity_triggers_vision_check(self, daemon):
        """After inactivity_timeout, the daemon should query VisionAdapter."""
        daemon._inactivity_timeout = 0  # make it trigger immediately
        daemon._last_activity_ts = 0.0

        mock_vision = MagicMock()
        mock_vision.capture_and_analyze.return_value = "sim"

        with patch("app.adapters.infrastructure.overwatch_adapter.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_vision
            with patch.object(daemon, "_suggest_pending_task") as mock_suggest:
                daemon._check_inactivity()

        mock_suggest.assert_called_once()
