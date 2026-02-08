# -*- coding: utf-8 -*-
"""Tests for GitHub Adapter"""

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.infrastructure.github_adapter import GitHubAdapter


class TestGitHubAdapter:
    """Test cases for GitHubAdapter"""

    @pytest.fixture
    def mock_env(self):
        """Mock environment variables"""
        with patch.dict(os.environ, {
            "GITHUB_TOKEN": "test_token_12345",
            "GITHUB_REPOSITORY": "test-owner/test-repo"
        }):
            yield

    @pytest.fixture
    def adapter(self, mock_env):
        """Create an adapter instance"""
        return GitHubAdapter()

    def test_initialization(self, adapter):
        """Test adapter initialization"""
        assert adapter.token == "test_token_12345"
        assert adapter.repo_owner == "test-owner"
        assert adapter.repo_name == "test-repo"
        assert adapter.base_url == "https://api.github.com"

    def test_initialization_without_token(self):
        """Test adapter initialization without token"""
        with patch.dict(os.environ, {}, clear=True):
            adapter = GitHubAdapter()
            assert adapter.token is None

    def test_initialization_with_custom_params(self):
        """Test adapter initialization with custom parameters"""
        adapter = GitHubAdapter(
            token="custom_token",
            repo_owner="custom-owner",
            repo_name="custom-repo"
        )
        assert adapter.token == "custom_token"
        assert adapter.repo_owner == "custom-owner"
        assert adapter.repo_name == "custom-repo"

    def test_get_headers(self, adapter):
        """Test HTTP headers generation"""
        headers = adapter._get_headers()
        
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"
        assert headers["Authorization"] == "Bearer test_token_12345"

    def test_get_headers_without_token(self):
        """Test HTTP headers generation without token"""
        with patch.dict(os.environ, {}, clear=True):
            adapter = GitHubAdapter()
            headers = adapter._get_headers()
            
            assert "Authorization" not in headers
            assert headers["Accept"] == "application/vnd.github+json"

    @pytest.mark.anyio
    async def test_dispatch_auto_fix_success(self, adapter):
        """Test successful auto-fix dispatch"""
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 204
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            issue_data = {
                "issue_title": "Fix test error",
                "file_path": "app/test.py",
                "fix_code": "print('fixed')",
                "test_command": "pytest tests/test.py"
            }
            
            result = await adapter.dispatch_auto_fix(issue_data)
            
            assert result["success"] is True
            assert "workflow_url" in result
            assert "test-owner/test-repo" in result["workflow_url"]
            
            # Verify the request was made with correct payload
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            
            # Check URL
            assert "/repos/test-owner/test-repo/dispatches" in call_args[0][0]
            
            # Check payload
            payload = call_args[1]["json"]
            assert payload["event_type"] == "auto_fix"
            assert payload["client_payload"]["issue_title"] == "Fix test error"
            assert payload["client_payload"]["file_path"] == "app/test.py"
            
            # Verify fix_code is base64 encoded
            encoded_fix = payload["client_payload"]["fix_code"]
            decoded_fix = base64.b64decode(encoded_fix).decode("utf-8")
            assert decoded_fix == "print('fixed')"

    @pytest.mark.anyio
    async def test_dispatch_auto_fix_without_token(self):
        """Test auto-fix dispatch without token"""
        with patch.dict(os.environ, {}, clear=True):
            adapter = GitHubAdapter()
            
            issue_data = {
                "issue_title": "Fix test error",
                "file_path": "app/test.py",
                "fix_code": "print('fixed')"
            }
            
            result = await adapter.dispatch_auto_fix(issue_data)
            
            assert result["success"] is False
            assert "GITHUB_TOKEN not configured" in result["error"]

    @pytest.mark.anyio
    async def test_dispatch_auto_fix_missing_fields(self, adapter):
        """Test auto-fix dispatch with missing required fields"""
        # Missing file_path
        issue_data = {
            "issue_title": "Fix test error",
            "fix_code": "print('fixed')"
        }
        
        result = await adapter.dispatch_auto_fix(issue_data)
        
        assert result["success"] is False
        assert "Missing required field" in result["error"]

    @pytest.mark.anyio
    async def test_dispatch_auto_fix_api_error(self, adapter):
        """Test auto-fix dispatch with API error"""
        # Mock httpx response with error
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            issue_data = {
                "issue_title": "Fix test error",
                "file_path": "app/test.py",
                "fix_code": "print('fixed')"
            }
            
            result = await adapter.dispatch_auto_fix(issue_data)
            
            assert result["success"] is False
            assert "401" in result["error"]
            assert "Unauthorized" in result["error"]

    @pytest.mark.anyio
    async def test_dispatch_auto_fix_exception(self, adapter):
        """Test auto-fix dispatch with exception"""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            issue_data = {
                "issue_title": "Fix test error",
                "file_path": "app/test.py",
                "fix_code": "print('fixed')"
            }
            
            result = await adapter.dispatch_auto_fix(issue_data)
            
            assert result["success"] is False
            assert "Network error" in result["error"]

    @pytest.mark.anyio
    async def test_get_workflow_runs_success(self, adapter):
        """Test getting workflow runs"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_count": 1,
            "workflow_runs": [{"id": 123, "status": "completed"}]
        }
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            result = await adapter.get_workflow_runs()
            
            assert result["success"] is True
            assert "data" in result
            assert result["data"]["total_count"] == 1

    @pytest.mark.anyio
    async def test_ensure_client_creates_client(self, adapter):
        """Test that _ensure_client creates a new client"""
        assert adapter._client is None
        
        client = await adapter._ensure_client()
        
        assert client is not None
        assert adapter._client is client

    @pytest.mark.anyio
    async def test_close_client(self, adapter):
        """Test closing the HTTP client"""
        # Create a client first
        await adapter._ensure_client()
        assert adapter._client is not None
        
        # Close it
        await adapter.close()
        assert adapter._client is None

    @pytest.mark.anyio
    async def test_dispatch_with_optional_test_command(self, adapter):
        """Test dispatch with optional test_command"""
        mock_response = MagicMock()
        mock_response.status_code = 204
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            # Without test_command
            issue_data = {
                "issue_title": "Fix test error",
                "file_path": "app/test.py",
                "fix_code": "print('fixed')"
            }
            
            result = await adapter.dispatch_auto_fix(issue_data)
            
            assert result["success"] is True
            
            # Verify test_command is empty string in payload
            payload = mock_client.post.call_args[1]["json"]
            assert payload["client_payload"]["test_command"] == ""

    @pytest.mark.anyio
    async def test_create_issue_success(self, adapter):
        """Test successful issue creation"""
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 42,
            "html_url": "https://github.com/test-owner/test-repo/issues/42"
        }
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            result = await adapter.create_issue(
                title="Botão X está quebrado",
                description="O botão X não responde quando clicado",
                error_log="ValueError: Invalid button state",
                system_info={"version": "1.0.0", "platform": "Linux"}
            )
            
            assert result["success"] is True
            assert result["issue_number"] == 42
            assert "github.com" in result["issue_url"]
            
            # Verify the request was made with correct payload
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            
            # Check URL
            assert "/repos/test-owner/test-repo/issues" in call_args[0][0]
            
            # Check payload
            payload = call_args[1]["json"]
            assert payload["title"] == "Botão X está quebrado"
            assert "O botão X não responde quando clicado" in payload["body"]
            assert "ValueError: Invalid button state" in payload["body"]
            assert "version" in payload["body"]
            assert "jarvis-auto-report" in payload["labels"]

    @pytest.mark.anyio
    async def test_create_issue_without_token(self):
        """Test issue creation without token"""
        with patch.dict(os.environ, {}, clear=True):
            adapter = GitHubAdapter()
            
            result = await adapter.create_issue(
                title="Test issue",
                description="Test description"
            )
            
            assert result["success"] is False
            assert "GITHUB_TOKEN not configured" in result["error"]

    @pytest.mark.anyio
    async def test_create_issue_api_error(self, adapter):
        """Test issue creation with API error"""
        # Mock httpx response with error
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            result = await adapter.create_issue(
                title="Test issue",
                description="Test description"
            )
            
            assert result["success"] is False
            assert "403" in result["error"]

    @pytest.mark.anyio
    async def test_create_issue_without_optional_params(self, adapter):
        """Test issue creation without optional parameters"""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 43,
            "html_url": "https://github.com/test-owner/test-repo/issues/43"
        }
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False
        
        with patch.object(adapter, '_ensure_client', return_value=mock_client):
            result = await adapter.create_issue(
                title="Simple issue",
                description="Simple description"
            )
            
            assert result["success"] is True
            assert result["issue_number"] == 43
            
            # Verify body doesn't contain error log or system info sections
            payload = mock_client.post.call_args[1]["json"]
            assert "## Erro" not in payload["body"]
            assert "## Informações do Sistema" not in payload["body"]
            assert "Simple description" in payload["body"]
