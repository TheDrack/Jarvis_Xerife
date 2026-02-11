# -*- coding: utf-8 -*-
"""Tests for API Server"""

from unittest.mock import Mock, AsyncMock, ANY

import pytest
from fastapi.testclient import TestClient

from app.adapters.infrastructure import create_api_server
from app.application.services import AssistantService
from app.domain.models import Response


class TestAPIServer:
    """Test cases for FastAPI server"""

    @pytest.fixture
    def mock_assistant_service(self):
        """Create a mocked AssistantService"""
        service = Mock(spec=AssistantService)
        service.wake_word = "xerife"
        service.is_running = False
        service._command_history = []
        # Add interpreter mock for distributed mode
        service.interpreter = Mock()
        return service

    @pytest.fixture
    def client(self, mock_assistant_service):
        """Create a test client with mocked service"""
        app = create_api_server(mock_assistant_service)
        return TestClient(app), mock_assistant_service

    @pytest.fixture
    def auth_token(self, client):
        """Get authentication token for protected endpoints"""
        test_client, _ = client
        response = test_client.post(
            "/token",
            data={"username": "admin", "password": "admin123"},
        )
        return response.json()["access_token"]

    def test_root_get(self, client):
        """Test root GET endpoint returns HTML interface with login and voice"""
        test_client, service = client
        
        response = test_client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Verify it contains key elements of the Stark Industries interface
        assert "J.A.R.V.I.S." in response.text
        assert "/v1/message" in response.text  # Now uses message endpoint
        assert "<!DOCTYPE html>" in response.text
        # Verify new features
        assert "loginModal" in response.text
        assert "voiceButton" in response.text
        assert "SpeechRecognition" in response.text
        assert "logout" in response.text.lower()
        # Verify password toggle
        assert "passwordToggle" in response.text
        # Verify voice synthesis
        assert "speechSynthesis" in response.text
        # Verify reactor loading animation
        assert "reactor" in response.text
    
    def test_root_head(self, client):
        """Test root HEAD endpoint for monitoring"""
        test_client, service = client
        
        response = test_client.head("/")

        assert response.status_code == 200
        # HEAD requests should not return a body per HTTP specification
        assert len(response.content) == 0
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        test_client, service = client
        
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        
        # Validate enhanced health check response
        assert "status" in data
        assert "version" in data
        assert data["version"] == "1.0.0"
        assert "database" in data
        assert "security" in data
        
        # For SQLite (default in tests), RLS should be N/A
        if data["database"]["type"] == "sqlite":
            assert data["security"]["rls_enabled"] == "n/a"
            assert "note" in data["security"]

    def test_login_success(self, client):
        """Test successful login"""
        test_client, _ = client

        response = test_client.post(
            "/token",
            data={"username": "admin", "password": "admin123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_password(self, client):
        """Test login with invalid password"""
        test_client, _ = client

        response = test_client.post(
            "/token",
            data={"username": "admin", "password": "wrongpassword"},
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_login_invalid_username(self, client):
        """Test login with invalid username"""
        test_client, _ = client

        response = test_client.post(
            "/token",
            data={"username": "nonexistent", "password": "password"},
        )

        assert response.status_code == 401
        assert "Incorrect username or password" in response.json()["detail"]

    def test_execute_command_without_auth(self, client):
        """Test execute endpoint requires authentication"""
        test_client, _ = client

        response = test_client.post(
            "/v1/execute",
            json={"command": "escreva hello"},
        )

        assert response.status_code == 401
        assert "detail" in response.json()

    def test_execute_command_with_invalid_token(self, client):
        """Test execute endpoint with invalid token"""
        test_client, _ = client

        response = test_client.post(
            "/v1/execute",
            json={"command": "escreva hello"},
            headers={"Authorization": "Bearer invalid_token"},
        )

        assert response.status_code == 401

    def test_execute_command_success(self, client, auth_token):
        """Test successful command execution with authentication"""
        test_client, service = client

        # Mock successful response using AsyncMock for async_process_command
        service.async_process_command = AsyncMock(return_value=Response(
            success=True,
            message="Command executed",
            data={"result": "ok"},
        ))

        response = test_client.post(
            "/v1/execute",
            json={"command": "escreva hello"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Command executed"
        assert data["data"] == {"result": "ok"}
        service.async_process_command.assert_called_once_with("escreva hello", request_metadata=ANY)

    def test_execute_command_failure(self, client, auth_token):
        """Test failed command execution"""
        test_client, service = client

        # Mock failed response using AsyncMock for async_process_command
        service.async_process_command = AsyncMock(return_value=Response(
            success=False,
            message="Invalid command",
            error="UNKNOWN_COMMAND",
        ))

        response = test_client.post(
            "/v1/execute",
            json={"command": "invalid command"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "Invalid command"
        assert data["error"] == "UNKNOWN_COMMAND"

    def test_execute_command_empty(self, client, auth_token):
        """Test command execution with empty command"""
        test_client, _ = client

        response = test_client.post(
            "/v1/execute",
            json={"command": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Should fail validation (min_length=1)
        assert response.status_code == 422

    def test_execute_command_exception(self, client, auth_token):
        """Test command execution with exception"""
        test_client, service = client

        # Mock exception using AsyncMock for async_process_command
        service.async_process_command = AsyncMock(side_effect=Exception("Test error"))

        response = test_client.post(
            "/v1/execute",
            json={"command": "test"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]

    def test_get_status(self, client):
        """Test status endpoint"""
        test_client, service = client

        service.is_running = True

        response = test_client.get("/v1/status")

        assert response.status_code == 200
        data = response.json()
        assert data["app_name"] == "Jarvis Assistant"
        assert "version" in data
        assert data["is_active"] is True
        assert data["wake_word"] == "xerife"
        assert data["language"] == "pt-BR"

    def test_get_history_empty(self, client):
        """Test history endpoint with no commands"""
        test_client, service = client

        service.get_command_history.return_value = []

        response = test_client.get("/v1/history")

        assert response.status_code == 200
        data = response.json()
        assert data["commands"] == []
        assert data["total"] == 0

    def test_get_history_with_commands(self, client):
        """Test history endpoint with commands"""
        test_client, service = client

        service.get_command_history.return_value = [
            {
                "command": "escreva hello",
                "timestamp": "2024-01-01T00:00:00Z",
                "success": True,
                "message": "Typed: hello",
            },
            {
                "command": "aperte enter",
                "timestamp": "2024-01-01T00:00:01Z",
                "success": True,
                "message": "Pressed: enter",
            },
        ]

        response = test_client.get("/v1/history")

        assert response.status_code == 200
        data = response.json()
        assert len(data["commands"]) == 2
        assert data["total"] == 2
        assert data["commands"][0]["command"] == "escreva hello"
        assert data["commands"][1]["command"] == "aperte enter"

    def test_get_history_with_limit(self, client):
        """Test history endpoint with limit parameter"""
        test_client, service = client

        service.get_command_history.return_value = [
            {
                "command": "command1",
                "timestamp": "2024-01-01T00:00:00Z",
                "success": True,
                "message": "ok",
            },
        ]

        response = test_client.get("/v1/history?limit=10")

        assert response.status_code == 200
        service.get_command_history.assert_called_once_with(limit=10)

    def test_get_history_limit_validation(self, client):
        """Test history endpoint limit is capped"""
        test_client, service = client

        service.get_command_history.return_value = []

        # Should cap at 50
        response = test_client.get("/v1/history?limit=100")

        assert response.status_code == 200
        service.get_command_history.assert_called_once_with(limit=50)

    def test_api_documentation(self, client):
        """Test that API documentation is available"""
        test_client, _ = client

        response = test_client.get("/docs")
        assert response.status_code == 200

        response = test_client.get("/openapi.json")
        assert response.status_code == 200
        assert "openapi" in response.json()

    def test_create_task_without_auth(self, client):
        """Test task creation endpoint requires authentication"""
        test_client, _ = client

        response = test_client.post(
            "/v1/task",
            json={"command": "digite hello"},
        )

        assert response.status_code == 401

    def test_create_task_success(self, client, auth_token):
        """Test successful task creation for distributed mode"""
        test_client, service = client

        # Mock interpreter
        from app.domain.models import CommandType, Intent
        
        mock_intent = Intent(
            command_type=CommandType.TYPE_TEXT,
            parameters={"text": "hello"},
            raw_input="digite hello",
        )
        service.interpreter.interpret.return_value = mock_intent

        response = test_client.post(
            "/v1/task",
            json={"command": "digite hello"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert isinstance(data["task_id"], int)
        assert data["status"] == "pending"
        assert "Task created successfully" in data["message"]

    def test_create_task_empty_command(self, client, auth_token):
        """Test task creation with empty command"""
        test_client, _ = client

        response = test_client.post(
            "/v1/task",
            json={"command": ""},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Should fail validation (min_length=1)
        assert response.status_code == 422

    def test_create_task_exception(self, client, auth_token):
        """Test task creation with exception"""
        test_client, service = client

        # Mock exception
        service.interpreter.interpret.side_effect = Exception("Test error")

        response = test_client.post(
            "/v1/task",
            json={"command": "test"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


class TestJarvisDispatchEndpoint:
    """Test cases for Jarvis repository_dispatch endpoint"""

    @pytest.fixture
    def mock_assistant_service(self):
        """Create a mocked AssistantService"""
        service = Mock(spec=AssistantService)
        service.wake_word = "xerife"
        service.is_running = False
        service._command_history = []
        service.interpreter = Mock()
        return service

    @pytest.fixture
    def mock_github_worker(self):
        """Create a mocked GitHubWorker"""
        from unittest.mock import Mock
        worker = Mock()
        worker.trigger_repository_dispatch = Mock()
        return worker

    @pytest.fixture
    def client(self, mock_assistant_service, mock_github_worker):
        """Create a test client with mocked service"""
        from unittest.mock import patch
        
        # Patch GitHubWorker at the import location
        with patch('app.application.services.github_worker.GitHubWorker', return_value=mock_github_worker):
            app = create_api_server(mock_assistant_service)
            test_client = TestClient(app)
            yield test_client, mock_assistant_service, mock_github_worker

    @pytest.fixture
    def auth_token(self, client):
        """Get authentication token for protected endpoints"""
        test_client, _, _ = client
        response = test_client.post(
            "/token",
            data={"username": "admin", "password": "admin123"},
        )
        return response.json()["access_token"]

    def test_jarvis_dispatch_create_success(self, client, auth_token):
        """Test Jarvis dispatch with create intent"""
        test_client, _, mock_worker = client

        mock_worker.trigger_repository_dispatch.return_value = {
            "success": True,
            "message": "Dispatch triggered successfully",
            "workflow_url": "https://github.com/user/repo/actions",
        }

        response = test_client.post(
            "/v1/jarvis/dispatch",
            json={
                "intent": "create",
                "instruction": "Add a new feature for user authentication",
                "context": "In the auth module",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "triggered successfully" in data["message"]
        assert data["workflow_url"] == "https://github.com/user/repo/actions"

    def test_jarvis_dispatch_fix_success(self, client, auth_token):
        """Test Jarvis dispatch with fix intent"""
        test_client, _, mock_worker = client

        mock_worker.trigger_repository_dispatch.return_value = {
            "success": True,
            "message": "Dispatch triggered successfully",
            "workflow_url": "https://github.com/user/repo/actions",
        }

        response = test_client.post(
            "/v1/jarvis/dispatch",
            json={
                "intent": "fix",
                "instruction": "Fix the bug in the login endpoint",
                "context": "Tests are failing",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_jarvis_dispatch_invalid_intent(self, client, auth_token):
        """Test Jarvis dispatch with invalid intent"""
        test_client, _, _ = client

        response = test_client.post(
            "/v1/jarvis/dispatch",
            json={
                "intent": "invalid",
                "instruction": "Do something",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Should fail validation
        assert response.status_code == 422

    def test_jarvis_dispatch_missing_instruction(self, client, auth_token):
        """Test Jarvis dispatch without instruction"""
        test_client, _, _ = client

        response = test_client.post(
            "/v1/jarvis/dispatch",
            json={
                "intent": "create",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        # Should fail validation
        assert response.status_code == 422

    def test_jarvis_dispatch_without_auth(self, client):
        """Test Jarvis dispatch requires authentication"""
        test_client, _, _ = client

        response = test_client.post(
            "/v1/jarvis/dispatch",
            json={
                "intent": "create",
                "instruction": "Add a new feature",
            },
        )

        assert response.status_code == 401

    def test_jarvis_dispatch_github_worker_failure(self, client, auth_token):
        """Test Jarvis dispatch when GitHub worker fails"""
        test_client, _, mock_worker = client

        mock_worker.trigger_repository_dispatch.return_value = {
            "success": False,
            "message": "GITHUB_PAT not configured",
        }

        response = test_client.post(
            "/v1/jarvis/dispatch",
            json={
                "intent": "create",
                "instruction": "Add a new feature",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 500
        assert "GITHUB_PAT" in response.json()["detail"]

    def test_jarvis_dispatch_with_context(self, client, auth_token):
        """Test Jarvis dispatch with context"""
        test_client, _, mock_worker = client

        mock_worker.trigger_repository_dispatch.return_value = {
            "success": True,
            "message": "Dispatch triggered successfully",
            "workflow_url": "https://github.com/user/repo/actions",
        }

        response = test_client.post(
            "/v1/jarvis/dispatch",
            json={
                "intent": "create",
                "instruction": "Add logging to all endpoints",
                "context": "Use structured logging with timestamps",
            },
            headers={"Authorization": f"Bearer {auth_token}"},
        )

        assert response.status_code == 200
        
        # Verify the payload sent to GitHub worker
        call_args = mock_worker.trigger_repository_dispatch.call_args
        assert call_args[1]["event_type"] == "jarvis_order"
        payload = call_args[1]["client_payload"]
        assert payload["intent"] == "create"
        assert payload["instruction"] == "Add logging to all endpoints"
        assert payload["context"] == "Use structured logging with timestamps"
        assert payload["triggered_by"] == "admin"

