# -*- coding: utf-8 -*-
"""Tests for Gateway LLM Adapter auto-repair security mechanism"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from app.adapters.infrastructure.gateway_llm_adapter import GatewayLLMCommandAdapter


class TestGatewayLLMAutoRepair:
    """Test cases for auto-repair security mechanism in GatewayLLMCommandAdapter"""

    @pytest.fixture
    def mock_github_adapter(self):
        """Mock GitHub adapter"""
        adapter = MagicMock()
        adapter.dispatch_auto_fix = AsyncMock(
            return_value={"success": True, "workflow_url": "https://github.com/test"}
        )
        return adapter

    @pytest.fixture
    def gateway_adapter(self, mock_github_adapter):
        """Create a gateway adapter instance with mocked dependencies"""
        with patch.dict('os.environ', {
            'GROQ_API_KEY': 'test_groq_key',
            'GOOGLE_API_KEY': 'test_gemini_key'
        }):
            with patch('app.adapters.infrastructure.gateway_llm_adapter.GitHubAdapter', return_value=mock_github_adapter):
                adapter = GatewayLLMCommandAdapter(use_llm=True)
                # Replace the github_adapter with our mock
                adapter.github_adapter = mock_github_adapter
                return adapter

    @pytest.mark.anyio
    async def test_auto_repair_logs_error_locally(self, gateway_adapter):
        """Test that errors are logged locally to prevent infinite loops"""
        error_traceback = "Traceback (most recent call last):\n  File test.py, line 10\nTypeError: test error"
        
        # Mock file writing
        with patch('builtins.open', mock_open()) as mock_file:
            gateway_adapter._log_error_locally(error_traceback)
            
            # Verify file was opened for appending
            mock_file.assert_called_once()
            call_args = mock_file.call_args
            assert '/tmp/jarvis_auto_repair_errors.log' in str(call_args)
            assert 'a' in str(call_args)

    @pytest.mark.anyio
    async def test_auto_repair_sends_to_gemini_when_use_llm_true(self, gateway_adapter, mock_github_adapter):
        """Test that errors are sent to Gemini for analysis when use_llm is True"""
        error_traceback = "Traceback (most recent call last):\n  File test.py, line 10\nTypeError: test error"
        user_input = "test command"
        
        # Mock Gemini response with valid JSON
        gemini_response = {
            "file_path": "app/test.py",
            "original_code": "old code",
            "fix_code": "new code"
        }
        
        mock_result = {
            "provider": "gemini",
            "response": MagicMock(
                candidates=[
                    MagicMock(
                        content=MagicMock(
                            parts=[MagicMock(text=json.dumps(gemini_response))]
                        )
                    )
                ]
            )
        }
        
        with patch.object(gateway_adapter.gateway, 'generate_completion', return_value=mock_result):
            with patch.object(gateway_adapter, '_log_error_locally'):
                await gateway_adapter._attempt_auto_repair(error_traceback, user_input)
                
                # Verify Gemini was called with correct instruction
                gateway_adapter.gateway.generate_completion.assert_called_once()
                call_args = gateway_adapter.gateway.generate_completion.call_args
                messages = call_args[1]['messages']
                
                # Check that the instruction contains required text
                assert len(messages) == 1
                assert 'Analise este erro de sistema' in messages[0]['content']
                assert 'file_path' in messages[0]['content']
                assert 'original_code' in messages[0]['content']
                assert 'fix_code' in messages[0]['content']
                assert error_traceback in messages[0]['content']

    @pytest.mark.anyio
    async def test_auto_repair_calls_github_dispatch(self, gateway_adapter, mock_github_adapter):
        """Test that auto-repair calls github_adapter.dispatch_auto_fix with parsed JSON"""
        error_traceback = "Traceback (most recent call last):\n  File test.py, line 10\nTypeError: test error"
        user_input = "test command"
        
        # Mock Gemini response
        gemini_response = {
            "file_path": "app/test.py",
            "original_code": "old code",
            "fix_code": "new code"
        }
        
        mock_result = {
            "provider": "gemini",
            "response": MagicMock(
                candidates=[
                    MagicMock(
                        content=MagicMock(
                            parts=[MagicMock(text=json.dumps(gemini_response))]
                        )
                    )
                ]
            )
        }
        
        with patch.object(gateway_adapter.gateway, 'generate_completion', return_value=mock_result):
            with patch.object(gateway_adapter, '_log_error_locally'):
                await gateway_adapter._attempt_auto_repair(error_traceback, user_input)
                
                # Verify dispatch_auto_fix was called
                mock_github_adapter.dispatch_auto_fix.assert_called_once()
                
                # Verify the correct data was passed
                call_args = mock_github_adapter.dispatch_auto_fix.call_args
                issue_data = call_args[0][0]
                
                assert 'issue_title' in issue_data
                assert 'file_path' in issue_data
                assert issue_data['file_path'] == 'app/test.py'
                assert issue_data['fix_code'] == 'new code'

    @pytest.mark.anyio
    async def test_auto_repair_handles_github_dispatch_failure(self, gateway_adapter, mock_github_adapter):
        """Test that GitHub dispatch failures are logged but don't raise exceptions"""
        # Make dispatch fail
        mock_github_adapter.dispatch_auto_fix = AsyncMock(
            return_value={"success": False, "error": "GitHub API error"}
        )
        
        error_traceback = "Traceback (most recent call last):\n  File test.py, line 10\nTypeError: test error"
        user_input = "test command"
        
        gemini_response = {
            "file_path": "app/test.py",
            "original_code": "old code",
            "fix_code": "new code"
        }
        
        mock_result = {
            "provider": "gemini",
            "response": MagicMock(
                candidates=[
                    MagicMock(
                        content=MagicMock(
                            parts=[MagicMock(text=json.dumps(gemini_response))]
                        )
                    )
                ]
            )
        }
        
        with patch.object(gateway_adapter.gateway, 'generate_completion', return_value=mock_result):
            with patch.object(gateway_adapter, '_log_error_locally') as mock_log:
                # Should not raise exception
                await gateway_adapter._attempt_auto_repair(error_traceback, user_input)
                
                # Verify error was logged locally
                assert mock_log.call_count >= 1
                # Check that at least one call contains the GitHub error
                logged_messages = [str(call[0][0]) for call in mock_log.call_args_list]
                assert any('GitHub' in msg for msg in logged_messages)

    @pytest.mark.anyio
    async def test_auto_repair_skipped_when_use_llm_false(self, mock_github_adapter):
        """Test that auto-repair is skipped when use_llm is False"""
        with patch.dict('os.environ', {
            'GROQ_API_KEY': 'test_groq_key',
            'GOOGLE_API_KEY': 'test_gemini_key'
        }):
            with patch('app.adapters.infrastructure.gateway_llm_adapter.GitHubAdapter', return_value=mock_github_adapter):
                adapter = GatewayLLMCommandAdapter(use_llm=False)
                adapter.github_adapter = mock_github_adapter
                
                # Mock the gateway to raise an error
                with patch.object(adapter.gateway, 'generate_completion', side_effect=Exception("test error")):
                    with patch.object(adapter, '_log_error_locally'):
                        with patch.object(adapter, '_attempt_auto_repair') as mock_repair:
                            response = await adapter.generate_conversational_response("test input")
                            
                            # Verify auto-repair was NOT called
                            mock_repair.assert_not_called()
                            
                            # Should still return error message
                            assert "erro" in response.lower()

    @pytest.mark.anyio
    async def test_auto_repair_with_markdown_wrapped_json(self, gateway_adapter, mock_github_adapter):
        """Test that auto-repair can handle JSON wrapped in markdown code blocks"""
        error_traceback = "Traceback (most recent call last):\n  File test.py, line 10\nTypeError: test error"
        user_input = "test command"
        
        gemini_response = {
            "file_path": "app/test.py",
            "original_code": "old code",
            "fix_code": "new code"
        }
        
        # Wrap in markdown code block
        markdown_wrapped = f"```json\n{json.dumps(gemini_response)}\n```"
        
        mock_result = {
            "provider": "gemini",
            "response": MagicMock(
                candidates=[
                    MagicMock(
                        content=MagicMock(
                            parts=[MagicMock(text=markdown_wrapped)]
                        )
                    )
                ]
            )
        }
        
        with patch.object(gateway_adapter.gateway, 'generate_completion', return_value=mock_result):
            with patch.object(gateway_adapter, '_log_error_locally'):
                await gateway_adapter._attempt_auto_repair(error_traceback, user_input)
                
                # Verify dispatch was called successfully despite markdown wrapping
                mock_github_adapter.dispatch_auto_fix.assert_called_once()

    @pytest.mark.anyio
    async def test_auto_repair_handles_invalid_json(self, gateway_adapter):
        """Test that auto-repair handles invalid JSON gracefully"""
        error_traceback = "Traceback (most recent call last):\n  File test.py, line 10\nTypeError: test error"
        user_input = "test command"
        
        # Invalid JSON response
        mock_result = {
            "provider": "gemini",
            "response": MagicMock(
                candidates=[
                    MagicMock(
                        content=MagicMock(
                            parts=[MagicMock(text="This is not valid JSON")]
                        )
                    )
                ]
            )
        }
        
        with patch.object(gateway_adapter.gateway, 'generate_completion', return_value=mock_result):
            with patch.object(gateway_adapter, '_log_error_locally') as mock_log:
                # Should not raise exception
                await gateway_adapter._attempt_auto_repair(error_traceback, user_input)
                
                # Verify error was logged
                assert mock_log.call_count >= 1

    @pytest.mark.anyio
    async def test_auto_repair_handles_missing_json_fields(self, gateway_adapter, mock_github_adapter):
        """Test that auto-repair handles JSON with missing required fields"""
        error_traceback = "Traceback (most recent call last):\n  File test.py, line 10\nTypeError: test error"
        user_input = "test command"
        
        # JSON with missing fields
        incomplete_response = {
            "file_path": "app/test.py"
            # Missing original_code and fix_code
        }
        
        mock_result = {
            "provider": "gemini",
            "response": MagicMock(
                candidates=[
                    MagicMock(
                        content=MagicMock(
                            parts=[MagicMock(text=json.dumps(incomplete_response))]
                        )
                    )
                ]
            )
        }
        
        with patch.object(gateway_adapter.gateway, 'generate_completion', return_value=mock_result):
            with patch.object(gateway_adapter, '_log_error_locally'):
                # Should not raise exception
                await gateway_adapter._attempt_auto_repair(error_traceback, user_input)
                
                # Verify dispatch was NOT called due to missing fields
                mock_github_adapter.dispatch_auto_fix.assert_not_called()

    @pytest.mark.anyio
    async def test_generate_response_calls_auto_repair_on_error(self, gateway_adapter):
        """Test that generate_conversational_response calls auto-repair on error"""
        # Mock gateway to raise an error
        with patch.object(gateway_adapter.gateway, 'generate_completion', side_effect=Exception("test error")):
            with patch.object(gateway_adapter, '_attempt_auto_repair') as mock_repair:
                with patch.object(gateway_adapter, '_log_error_locally'):
                    with patch.object(gateway_adapter, '_handle_critical_error'):
                        response = await gateway_adapter.generate_conversational_response("test input")
                        
                        # Verify auto-repair was called
                        mock_repair.assert_called_once()
                        
                        # Check arguments
                        call_args = mock_repair.call_args
                        assert 'test error' in call_args[0][0]  # error_traceback contains error
                        assert call_args[0][1] == 'test input'  # user_input
