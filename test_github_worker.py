# -*- coding: utf-8 -*-
"""Tests for GitHubWorker service"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess

from app.application.services.github_worker import GitHubWorker


@pytest.fixture
def github_worker(tmp_path):
    """Create a GitHubWorker instance for testing"""
    return GitHubWorker(repo_path=str(tmp_path))


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for testing"""
    with patch('subprocess.run') as mock_run:
        yield mock_run


def test_github_worker_initialization(tmp_path):
    """Test GitHubWorker initialization"""
    worker = GitHubWorker(repo_path=str(tmp_path))
    assert worker.repo_path == tmp_path


def test_check_gh_cli_success(github_worker, mock_subprocess):
    """Test checking gh CLI when it's installed and authenticated"""
    mock_subprocess.return_value = Mock(returncode=0, stdout="Logged in", stderr="")
    
    result = github_worker._check_gh_cli()
    
    assert result is True
    mock_subprocess.assert_called_once()


def test_check_gh_cli_not_authenticated(github_worker, mock_subprocess):
    """Test checking gh CLI when it's not authenticated"""
    mock_subprocess.return_value = Mock(returncode=1, stdout="", stderr="Not logged in")
    
    result = github_worker._check_gh_cli()
    
    assert result is False


def test_check_gh_cli_not_installed(github_worker, mock_subprocess):
    """Test checking gh CLI when it's not installed"""
    mock_subprocess.side_effect = FileNotFoundError("gh not found")
    
    result = github_worker._check_gh_cli()
    
    assert result is False


def test_create_feature_branch_success(github_worker, mock_subprocess):
    """Test creating a feature branch successfully"""
    mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")
    
    result = github_worker.create_feature_branch("feature/test-branch")
    
    assert result["success"] is True
    assert result["branch"] == "feature/test-branch"
    assert "feature/test-branch" in result["message"]


def test_create_feature_branch_failure(github_worker, mock_subprocess):
    """Test creating a feature branch when it fails"""
    mock_subprocess.return_value = Mock(returncode=1, stdout="", stderr="Branch already exists")
    
    result = github_worker.create_feature_branch("feature/existing-branch")
    
    assert result["success"] is False
    assert "Branch already exists" in result["message"]


def test_submit_pull_request_success(github_worker, mock_subprocess):
    """Test submitting a pull request successfully"""
    # Mock git commands success
    mock_subprocess.side_effect = [
        Mock(returncode=0),  # git add
        Mock(returncode=0),  # git commit
        Mock(returncode=0),  # git push
        Mock(returncode=0, stdout="https://github.com/user/repo/pull/123", stderr=""),  # gh pr create
    ]
    
    result = github_worker.submit_pull_request(
        title="Test PR",
        body="Test description",
    )
    
    assert result["success"] is True
    assert "pr_url" in result
    assert "github.com" in result["pr_url"]


def test_submit_pull_request_push_failure(github_worker, mock_subprocess):
    """Test submitting a pull request when push fails"""
    mock_subprocess.side_effect = [
        Mock(returncode=0),  # git add
        Mock(returncode=0),  # git commit
        Mock(returncode=1, stdout="", stderr="Push failed"),  # git push
    ]
    
    result = github_worker.submit_pull_request(
        title="Test PR",
        body="Test description",
    )
    
    assert result["success"] is False
    assert "Push failed" in result["message"]


def test_submit_pull_request_pr_creation_failure(github_worker, mock_subprocess):
    """Test submitting a pull request when PR creation fails"""
    mock_subprocess.side_effect = [
        Mock(returncode=0),  # git add
        Mock(returncode=0),  # git commit
        Mock(returncode=0),  # git push
        Mock(returncode=1, stdout="", stderr="PR creation failed"),  # gh pr create
    ]
    
    result = github_worker.submit_pull_request(
        title="Test PR",
        body="Test description",
    )
    
    assert result["success"] is False
    assert "PR creation failed" in result["message"]


def test_fetch_ci_status_with_run_id(github_worker, mock_subprocess):
    """Test fetching CI status with a specific run ID"""
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout='{"status": "completed", "conclusion": "success", "databaseId": 12345}',
        stderr=""
    )
    
    result = github_worker.fetch_ci_status(run_id=12345)
    
    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["conclusion"] == "success"
    assert result["failed"] is False
    assert result["run_id"] == 12345


def test_fetch_ci_status_failure(github_worker, mock_subprocess):
    """Test fetching CI status for a failed run"""
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout='{"status": "completed", "conclusion": "failure", "databaseId": 12346}',
        stderr=""
    )
    
    result = github_worker.fetch_ci_status(run_id=12346)
    
    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["conclusion"] == "failure"
    assert result["failed"] is True


def test_fetch_ci_status_no_runs(github_worker, mock_subprocess):
    """Test fetching CI status when no runs are found"""
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout='[]',
        stderr=""
    )
    
    result = github_worker.fetch_ci_status()
    
    assert result["success"] is True
    assert result["status"] == "no_runs"


def test_fetch_ci_status_command_failure(github_worker, mock_subprocess):
    """Test fetching CI status when gh command fails"""
    mock_subprocess.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="gh command failed"
    )
    
    result = github_worker.fetch_ci_status(run_id=12347)
    
    assert result["success"] is False
    assert "gh command failed" in result["message"]


def test_download_ci_logs_success(github_worker, mock_subprocess):
    """Test downloading CI logs successfully"""
    mock_logs = "Build log line 1\nBuild log line 2\nError: Test failed"
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout=mock_logs,
        stderr=""
    )
    
    result = github_worker.download_ci_logs(run_id=12348)
    
    assert result["success"] is True
    assert result["logs"] == mock_logs
    assert "Test failed" in result["logs"]


def test_download_ci_logs_failure(github_worker, mock_subprocess):
    """Test downloading CI logs when it fails"""
    mock_subprocess.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="Failed to download logs"
    )
    
    result = github_worker.download_ci_logs(run_id=12349)
    
    assert result["success"] is False
    assert "Failed to download logs" in result["message"]


def test_file_write_success(github_worker):
    """Test writing content to a file"""
    content = "print('Hello, World!')"
    
    result = github_worker.file_write("test.py", content)
    
    assert result["success"] is True
    assert "test.py" in result["message"]
    
    # Verify file was written
    written_file = github_worker.repo_path / "test.py"
    assert written_file.exists()
    assert written_file.read_text() == content


def test_file_write_creates_parent_directories(github_worker):
    """Test that file_write creates parent directories"""
    content = "# Test file"
    
    result = github_worker.file_write("subdir/nested/test.py", content)
    
    assert result["success"] is True
    
    # Verify file and directories were created
    written_file = github_worker.repo_path / "subdir" / "nested" / "test.py"
    assert written_file.exists()
    assert written_file.read_text() == content


def test_auto_heal_ci_failure_downloads_logs(github_worker, mock_subprocess):
    """Test auto-heal downloads CI logs"""
    from sqlmodel import create_engine, SQLModel
    from app.application.services.thought_log_service import ThoughtLogService
    
    # Setup
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    thought_log_service = ThoughtLogService(engine=engine)
    
    mock_logs = "Build failed: Error in test.py"
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout=mock_logs,
        stderr=""
    )
    
    result = github_worker.auto_heal_ci_failure(
        run_id=12350,
        mission_id="heal_test_1",
        thought_log_service=thought_log_service,
    )
    
    # Should have attempted to download logs
    assert "logs_analyzed" in result or "requires_human" in result
    
    # Verify thought was logged
    thoughts = thought_log_service.get_mission_thoughts("heal_test_1")
    assert len(thoughts) >= 1
    assert thoughts[0].mission_id == "heal_test_1"


def test_auto_heal_escalates_after_max_retries(github_worker, mock_subprocess):
    """Test auto-heal escalates to human after 3 failures"""
    from sqlmodel import create_engine, SQLModel
    from app.application.services.thought_log_service import ThoughtLogService
    
    # Setup
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    thought_log_service = ThoughtLogService(engine=engine)
    
    mission_id = "heal_test_2"
    
    # Create 3 failed attempts
    for i in range(3):
        thought_log_service.create_thought(
            mission_id=mission_id,
            session_id=f"ci_heal_{12351}",
            thought_process=f"Attempt {i+1}",
            problem_description="CI failed",
            solution_attempt=f"Solution {i+1}",
            success=False,
            error_message=f"Error {i+1}",
        )
    
    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout="Build failed",
        stderr=""
    )
    
    # Fourth attempt should escalate
    result = github_worker.auto_heal_ci_failure(
        run_id=12351,
        mission_id=mission_id,
        thought_log_service=thought_log_service,
    )
    
    # Should require human intervention
    assert result.get("requires_human") is True or result.get("success") is False
    
    # If escalated, should have consolidated log
    if result.get("requires_human"):
        assert "consolidated_log" in result


def test_auto_heal_log_download_failure(github_worker, mock_subprocess):
    """Test auto-heal when log download fails"""
    from sqlmodel import create_engine, SQLModel
    from app.application.services.thought_log_service import ThoughtLogService
    
    # Setup
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    thought_log_service = ThoughtLogService(engine=engine)
    
    mock_subprocess.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="Failed to download logs"
    )
    
    result = github_worker.auto_heal_ci_failure(
        run_id=12352,
        mission_id="heal_test_3",
        thought_log_service=thought_log_service,
    )
    
    assert result["success"] is False
    assert "Failed to download CI logs" in result["message"]


def test_trigger_repository_dispatch_success(github_worker, mock_subprocess, monkeypatch):
    """Test triggering repository_dispatch successfully"""
    # Mock environment variable
    monkeypatch.setenv("GITHUB_PAT", "test_token_123")
    
    # Mock subprocess calls
    mock_subprocess.side_effect = [
        # gh repo view --json nameWithOwner
        Mock(
            returncode=0,
            stdout='{"nameWithOwner": "user/repo"}',
            stderr=""
        ),
        # curl API call
        Mock(returncode=0, stdout="", stderr=""),
    ]
    
    client_payload = {
        "intent": "create",
        "instruction": "Add a new feature",
        "context": "In the main.py file",
    }
    
    result = github_worker.trigger_repository_dispatch(
        event_type="jarvis_order",
        client_payload=client_payload,
    )
    
    assert result["success"] is True
    assert "jarvis_order" in result["message"]
    assert result["workflow_url"] == "https://github.com/user/repo/actions"
    assert result["event_type"] == "jarvis_order"
    assert result["payload"] == client_payload


def test_trigger_repository_dispatch_no_token(github_worker, mock_subprocess, monkeypatch):
    """Test triggering repository_dispatch without GITHUB_PAT"""
    # Remove token from environment
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    
    result = github_worker.trigger_repository_dispatch(
        event_type="jarvis_order",
        client_payload={"test": "data"},
    )
    
    assert result["success"] is False
    assert "GITHUB_PAT" in result["message"]


def test_trigger_repository_dispatch_repo_info_failure(github_worker, mock_subprocess, monkeypatch):
    """Test triggering repository_dispatch when getting repo info fails"""
    monkeypatch.setenv("GITHUB_PAT", "test_token_123")
    
    mock_subprocess.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="Not a git repository"
    )
    
    result = github_worker.trigger_repository_dispatch(
        event_type="jarvis_order",
        client_payload={"test": "data"},
    )
    
    assert result["success"] is False
    assert "Failed to get repository info" in result["message"]


def test_trigger_repository_dispatch_api_failure(github_worker, mock_subprocess, monkeypatch):
    """Test triggering repository_dispatch when API call fails"""
    monkeypatch.setenv("GITHUB_PAT", "test_token_123")
    
    mock_subprocess.side_effect = [
        # gh repo view
        Mock(
            returncode=0,
            stdout='{"nameWithOwner": "user/repo"}',
            stderr=""
        ),
        # curl API call fails
        Mock(returncode=1, stdout="", stderr="API error: Unauthorized"),
    ]
    
    result = github_worker.trigger_repository_dispatch(
        event_type="jarvis_order",
        client_payload={"test": "data"},
    )
    
    assert result["success"] is False
    assert "Failed to trigger event" in result["message"]


def test_trigger_repository_dispatch_with_custom_token(github_worker, mock_subprocess):
    """Test triggering repository_dispatch with custom token"""
    # Mock subprocess calls
    mock_subprocess.side_effect = [
        Mock(
            returncode=0,
            stdout='{"nameWithOwner": "user/repo"}',
            stderr=""
        ),
        Mock(returncode=0, stdout="", stderr=""),
    ]
    
    result = github_worker.trigger_repository_dispatch(
        event_type="jarvis_order",
        client_payload={"test": "data"},
        github_token="custom_token_456",
    )
    
    assert result["success"] is True
    
    # Verify curl was called with custom token
    curl_call = mock_subprocess.call_args_list[1]
    assert "custom_token_456" in str(curl_call)
