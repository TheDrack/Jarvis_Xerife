# -*- coding: utf-8 -*-
"""Tests for Gateway LLM Adapter self-healing functionality"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.infrastructure.gateway_llm_adapter import GatewayLLMCommandAdapter


class TestGatewayLLMAdapterSelfHealing:
    """Test cases for self-healing functionality in GatewayLLMCommandAdapter"""

    @pytest.fixture
    def mock_github_adapter(self):
        """Mock GitHub adapter"""
        adapter = MagicMock()
        adapter.dispatch_auto_fix = AsyncMock(return_value={"success": True, "workflow_url": "https://github.com/test"})
        return adapter

    @pytest.fixture
    def gateway_adapter(self, mock_github_adapter):
        """Create a gateway adapter instance with mocked dependencies"""
        with patch.dict('os.environ', {
            'GROQ_API_KEY': 'test_groq_key',
            'GOOGLE_API_KEY': 'test_gemini_key'
        }):
            with patch('app.adapters.infrastructure.gateway_llm_adapter.GitHubAdapter', return_value=mock_github_adapter):
                adapter = GatewayLLMCommandAdapter()
                # Replace the github_adapter with our mock
                adapter.github_adapter = mock_github_adapter
                return adapter

    @pytest.mark.anyio
    async def test_handle_critical_error_model_decommissioned(self, gateway_adapter, mock_github_adapter):
        """Test handling of model_decommissioned error"""
        error = Exception("model has been decommissioned")
        user_input = "test command"
        
        # Mock the correction plan formulation
        with patch.object(
            gateway_adapter,
            '_formulate_correction_plan',
            return_value={
                "issue_title": "Fix model error",
                "file_path": "app/test.py",
                "fix_code": "fixed code",
                "test_command": "pytest"
            }
        ):
            await gateway_adapter._handle_critical_error(error, user_input)
            
            # Verify dispatch_auto_fix was called
            mock_github_adapter.dispatch_auto_fix.assert_called_once()

    @pytest.mark.anyio
    async def test_handle_critical_error_rate_limit(self, gateway_adapter, mock_github_adapter):
        """Test handling of rate limit error"""
        error = Exception("rate limit exceeded")
        user_input = "test command"
        
        # Mock the correction plan formulation
        with patch.object(
            gateway_adapter,
            '_formulate_correction_plan',
            return_value={
                "issue_title": "Fix rate limit",
                "file_path": "app/test.py",
                "fix_code": "fixed code",
                "test_command": "pytest"
            }
        ):
            await gateway_adapter._handle_critical_error(error, user_input)
            
            # Verify dispatch_auto_fix was called
            mock_github_adapter.dispatch_auto_fix.assert_called_once()

    @pytest.mark.anyio
    async def test_handle_critical_error_non_critical(self, gateway_adapter, mock_github_adapter):
        """Test that non-critical errors don't trigger self-healing"""
        error = Exception("regular error")
        user_input = "test command"
        
        await gateway_adapter._handle_critical_error(error, user_input)
        
        # Verify dispatch_auto_fix was NOT called
        mock_github_adapter.dispatch_auto_fix.assert_not_called()

    @pytest.mark.anyio
    async def test_handle_critical_error_no_github_adapter(self, gateway_adapter):
        """Test handling when GitHub adapter is not available"""
        gateway_adapter.github_adapter = None
        
        error = Exception("model has been decommissioned")
        user_input = "test command"
        
        # Should not raise exception even without github_adapter
        await gateway_adapter._handle_critical_error(error, user_input)

    @pytest.mark.anyio
    async def test_formulate_correction_plan_model_decommissioned(self, gateway_adapter):
        """Test correction plan formulation for model decommissioned error"""
        error = Exception("model has been decommissioned")
        user_input = "test command"
        
        # Mock Gemini response
        mock_result = {
            "provider": "gemini",
            "response": MagicMock(
                candidates=[
                    MagicMock(
                        content=MagicMock(
                            parts=[MagicMock(text="É possível auto-correção: sim\nArquivo afetado: app/adapters/infrastructure/gemini_adapter.py")]
                        )
                    )
                ]
            )
        }
        
        with patch.object(gateway_adapter.gateway, 'generate_completion', return_value=mock_result):
            # Mock file reading
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = 'model_name: str = "gemini-flash-latest"'
                
                plan = await gateway_adapter._formulate_correction_plan(error, user_input)
                
                assert plan is not None
                assert plan["issue_title"] == "Fix model_decommissioned error"
                assert "gemini_adapter.py" in plan["file_path"]
                assert plan["fix_code"]

    @pytest.mark.anyio
    async def test_formulate_correction_plan_no_gemini_adapter(self, gateway_adapter):
        """Test correction plan formulation without Gemini adapter"""
        gateway_adapter.gemini_adapter = None
        
        error = Exception("model has been decommissioned")
        user_input = "test command"
        
        plan = await gateway_adapter._formulate_correction_plan(error, user_input)
        
        # Should return None when Gemini adapter is not available
        assert plan is None

    @pytest.mark.anyio
    async def test_parse_fix_plan_model_decommissioned(self, gateway_adapter):
        """Test parsing fix plan for model decommissioned error"""
        error = Exception("model has been decommissioned")
        response = "É possível auto-correção: sim"
        
        # Mock file reading
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = 'model_name: str = "gemini-flash-latest"'
            
            plan = gateway_adapter._parse_fix_plan_from_response(response, error)
            
            assert plan is not None
            assert "gemini-2.0-flash-exp" in plan["fix_code"]

    @pytest.mark.anyio
    async def test_parse_fix_plan_unsupported_error(self, gateway_adapter):
        """Test parsing fix plan for unsupported error type"""
        error = Exception("some unknown error")
        response = "É possível auto-correção: sim"
        
        plan = gateway_adapter._parse_fix_plan_from_response(response, error)
        
        # Should return None for unsupported error types
        assert plan is None

    @pytest.mark.anyio
    async def test_critical_error_in_generate_response(self, gateway_adapter, mock_github_adapter):
        """Test that critical errors in generate_conversational_response trigger self-healing"""
        # Mock the gateway to raise a critical error
        with patch.object(
            gateway_adapter.gateway,
            'generate_completion',
            side_effect=Exception("model has been decommissioned")
        ):
            # Mock the correction plan
            with patch.object(
                gateway_adapter,
                '_formulate_correction_plan',
                return_value={
                    "issue_title": "Fix model error",
                    "file_path": "app/test.py",
                    "fix_code": "fixed code",
                    "test_command": "pytest"
                }
            ):
                response = await gateway_adapter.generate_conversational_response("test input")
                
                # Should return error message
                assert "erro" in response.lower()
                
                # Should have triggered self-healing
                mock_github_adapter.dispatch_auto_fix.assert_called_once()

    @pytest.mark.anyio
    async def test_dispatch_failure_logged(self, gateway_adapter, mock_github_adapter):
        """Test that dispatch failures are properly logged"""
        # Make dispatch fail
        mock_github_adapter.dispatch_auto_fix = AsyncMock(
            return_value={"success": False, "error": "API error"}
        )
        
        error = Exception("model has been decommissioned")
        user_input = "test command"
        
        with patch.object(
            gateway_adapter,
            '_formulate_correction_plan',
            return_value={
                "issue_title": "Fix model error",
                "file_path": "app/test.py",
                "fix_code": "fixed code",
                "test_command": "pytest"
            }
        ):
            # Should not raise exception, just log the error
            await gateway_adapter._handle_critical_error(error, user_input)
            
            # Verify dispatch was attempted
            mock_github_adapter.dispatch_auto_fix.assert_called_once()
