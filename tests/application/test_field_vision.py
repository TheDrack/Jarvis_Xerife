# -*- coding: utf-8 -*-
"""Tests for FieldVision – proactive log monitor and self-healing trigger."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.application.services.field_vision import FieldVision


@pytest.fixture
def log_file(tmp_path: Path) -> Path:
    """Path for a temporary log file."""
    return tmp_path / "jarvis.log"


@pytest.fixture
def fv(log_file: Path) -> FieldVision:
    """FieldVision instance with a temporary log file and fake credentials."""
    return FieldVision(
        log_file=str(log_file),
        github_token="fake-token",
        github_repo="owner/repo",
    )


class TestScanVitalsNoLog:
    def test_returns_success_when_log_missing(self, fv: FieldVision) -> None:
        result = fv.scan_vitals()
        assert result["success"] is True
        assert result["errors_detected"] is False
        assert result["action"] == "none"


class TestScanVitalsCleanLog:
    def test_returns_no_errors_on_clean_log(self, fv: FieldVision, log_file: Path) -> None:
        log_file.write_text("INFO Starting\nINFO All good\nDEBUG tick\n", encoding="utf-8")
        result = fv.scan_vitals()
        assert result["errors_detected"] is False
        assert result["action"] == "none"


class TestScanVitalsWithErrors:
    def test_triggers_workflow_when_no_memory_solution(
        self, fv: FieldVision, log_file: Path
    ) -> None:
        log_file.write_text("INFO start\nERROR something broke\nINFO end\n", encoding="utf-8")

        with (
            patch.object(fv, "_query_memory", return_value=[]) as mock_mem,
            patch.object(fv, "_trigger_self_healing", return_value=True) as mock_heal,
        ):
            result = fv.scan_vitals()

        assert result["errors_detected"] is True
        assert result["action"] == "workflow_dispatched"
        assert result["success"] is True
        mock_mem.assert_called_once()
        mock_heal.assert_called_once()

    def test_does_not_trigger_workflow_when_memory_has_solution(
        self, fv: FieldVision, log_file: Path
    ) -> None:
        log_file.write_text("CRITICAL database unreachable\n", encoding="utf-8")

        known = [{"user": "database error", "jarvis": "restart db"}]
        with (
            patch.object(fv, "_query_memory", return_value=known),
            patch.object(fv, "_trigger_self_healing") as mock_heal,
        ):
            result = fv.scan_vitals()

        assert result["errors_detected"] is True
        assert result["action"] == "memory_resolved"
        assert result["known_solutions"] == 1
        mock_heal.assert_not_called()

    def test_dispatch_failed_action_on_trigger_failure(
        self, fv: FieldVision, log_file: Path
    ) -> None:
        log_file.write_text("ERROR critical failure\n", encoding="utf-8")

        with (
            patch.object(fv, "_query_memory", return_value=[]),
            patch.object(fv, "_trigger_self_healing", return_value=False),
        ):
            result = fv.scan_vitals()

        assert result["action"] == "dispatch_failed"
        assert result["success"] is False


class TestTriggerSelfHealing:
    def test_returns_false_when_credentials_missing(self, log_file: Path) -> None:
        fv_no_creds = FieldVision(log_file=str(log_file), github_token=None, github_repo=None)
        assert fv_no_creds._trigger_self_healing("some error") is False

    def test_returns_true_on_http_204(self, fv: FieldVision) -> None:
        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            assert fv._trigger_self_healing("error log") is True

    def test_returns_false_on_http_error(self, fv: FieldVision) -> None:
        import urllib.error

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(url="", code=422, msg="Unprocessable", hdrs=None, fp=None),  # type: ignore[arg-type]
        ):
            assert fv._trigger_self_healing("error log") is False


class TestReadLogTail:
    def test_returns_last_50_lines(self, fv: FieldVision, log_file: Path) -> None:
        lines = [f"line {i}" for i in range(100)]
        log_file.write_text("\n".join(lines), encoding="utf-8")
        tail = fv._read_log_tail()
        assert len(tail) == 50
        assert tail[0] == "line 50"

    def test_returns_all_lines_when_fewer_than_50(self, fv: FieldVision, log_file: Path) -> None:
        log_file.write_text("line 1\nline 2\n", encoding="utf-8")
        tail = fv._read_log_tail()
        assert len(tail) == 2


class TestExtractErrors:
    def test_filters_error_and_critical_lines(self, fv: FieldVision) -> None:
        lines = ["INFO ok", "ERROR boom", "DEBUG skip", "CRITICAL meltdown"]
        errors = fv._extract_errors(lines)
        assert errors == ["ERROR boom", "CRITICAL meltdown"]

    def test_returns_empty_on_clean_lines(self, fv: FieldVision) -> None:
        lines = ["INFO all good", "DEBUG nothing here"]
        assert fv._extract_errors(lines) == []


class TestExecute:
    def test_execute_calls_scan_vitals(self, fv: FieldVision) -> None:
        with patch.object(fv, "scan_vitals", return_value={"success": True}) as mock_sv:
            result = fv.execute({})
        mock_sv.assert_called_once()
        assert result["success"] is True
