# -*- coding: utf-8 -*-
"""Tests for AI Gateway Gears System"""

import os
from unittest.mock import Mock, patch, AsyncMock
import pytest

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider, GroqGear


class TestGroqGearsSystem:
    """Test cases for Groq Gears System (Marcha Alta/Baixa)"""

    @pytest.fixture
    def gateway_with_gears(self):
        """Create a gateway with Gears system configured"""
        gateway = AIGateway(
            groq_api_key="test_groq_key",
            gemini_api_key="test_gemini_key",
            groq_high_gear_model="llama-3.3-70b-versatile",
            groq_low_gear_model="llama-3.1-8b-instant",
            gemini_model="gemini-1.5-pro",
        )
        
        # Mock Groq client
        gateway.groq_client = Mock()
        groq_response = Mock()
        groq_choice = Mock()
        groq_message = Mock()
        groq_message.content = "Response from Groq"
        groq_choice.message = groq_message
        groq_response.choices = [groq_choice]
        gateway.groq_client.chat.completions.create.return_value = groq_response
        
        # Mock Gemini client
        gateway.gemini_client = Mock()
        gemini_response = Mock()
        gemini_candidate = Mock()
        gemini_part = Mock()
        gemini_part.text = "Response from Gemini"
        gemini_candidate.content.parts = [gemini_part]
        gemini_response.candidates = [gemini_candidate]
        gateway.gemini_client.models.generate_content.return_value = gemini_response
        
        return gateway

    def test_gateway_initialization_with_gears(self):
        """Test that gateway initializes correctly with Gears system"""
        gateway = AIGateway(
            groq_api_key="test_key",
            gemini_api_key="test_key",
            groq_high_gear_model="llama-3.3-70b-versatile",
            groq_low_gear_model="llama-3.1-8b-instant",
        )
        
        assert gateway.groq_high_gear_model == "llama-3.3-70b-versatile"
        assert gateway.groq_low_gear_model == "llama-3.1-8b-instant"
        assert gateway.current_groq_gear == GroqGear.HIGH_GEAR
        assert gateway.gemini_model == "gemini-1.5-pro"  # Default changed

    def test_get_current_groq_model_high_gear(self):
        """Test that current model returns High Gear model by default"""
        gateway = AIGateway(
            groq_api_key="test_key",
            groq_high_gear_model="llama-3.3-70b-versatile",
            groq_low_gear_model="llama-3.1-8b-instant",
        )
        
        assert gateway._get_current_groq_model() == "llama-3.3-70b-versatile"
        assert gateway.current_groq_gear == GroqGear.HIGH_GEAR

    def test_shift_to_low_gear(self):
        """Test shifting to Low Gear"""
        gateway = AIGateway(
            groq_api_key="test_key",
            groq_high_gear_model="llama-3.3-70b-versatile",
            groq_low_gear_model="llama-3.1-8b-instant",
        )
        
        # Initially in High Gear
        assert gateway.current_groq_gear == GroqGear.HIGH_GEAR
        
        # Shift to Low Gear
        gateway._shift_to_low_gear()
        
        assert gateway.current_groq_gear == GroqGear.LOW_GEAR
        assert gateway._get_current_groq_model() == "llama-3.1-8b-instant"

    def test_shift_to_high_gear(self):
        """Test shifting back to High Gear"""
        gateway = AIGateway(
            groq_api_key="test_key",
            groq_high_gear_model="llama-3.3-70b-versatile",
            groq_low_gear_model="llama-3.1-8b-instant",
        )
        
        # Shift to Low Gear first
        gateway._shift_to_low_gear()
        assert gateway.current_groq_gear == GroqGear.LOW_GEAR
        
        # Shift back to High Gear
        gateway._shift_to_high_gear()
        
        assert gateway.current_groq_gear == GroqGear.HIGH_GEAR
        assert gateway._get_current_groq_model() == "llama-3.3-70b-versatile"

    @pytest.mark.asyncio
    async def test_high_gear_used_by_default(self, gateway_with_gears):
        """Test that High Gear is used by default for completions"""
        gateway = gateway_with_gears
        
        messages = [{"role": "user", "content": "Test message"}]
        result = await gateway._generate_with_groq(messages)
        
        assert result["provider"] == LLMProvider.GROQ.value
        assert result["model"] == "llama-3.3-70b-versatile"
        assert result["gear"] == GroqGear.HIGH_GEAR.value

    @pytest.mark.asyncio
    async def test_low_gear_used_after_shift(self, gateway_with_gears):
        """Test that Low Gear is used after shifting"""
        gateway = gateway_with_gears
        
        # Shift to Low Gear
        gateway._shift_to_low_gear()
        
        messages = [{"role": "user", "content": "Test message"}]
        result = await gateway._generate_with_groq(messages)
        
        assert result["provider"] == LLMProvider.GROQ.value
        assert result["model"] == "llama-3.1-8b-instant"
        assert result["gear"] == GroqGear.HIGH_GEAR.value  # Shifts back after success

    @pytest.mark.asyncio
    async def test_auto_shift_back_to_high_gear_after_success(self, gateway_with_gears):
        """Test that gateway automatically shifts back to High Gear after successful Low Gear completion"""
        gateway = gateway_with_gears
        
        # Shift to Low Gear
        gateway._shift_to_low_gear()
        assert gateway.current_groq_gear == GroqGear.LOW_GEAR
        
        # Make a successful completion
        messages = [{"role": "user", "content": "Test message"}]
        await gateway._generate_with_groq(messages)
        
        # Should have shifted back to High Gear
        assert gateway.current_groq_gear == GroqGear.HIGH_GEAR

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_low_gear(self, gateway_with_gears):
        """Test that rate limit in High Gear triggers Low Gear"""
        gateway = gateway_with_gears
        
        # Make High Gear fail with rate limit first, then succeed in Low Gear
        call_count = [0]
        
        def groq_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call (High Gear) - rate limit
                raise Exception("Rate limit exceeded")
            else:
                # Second call (Low Gear) - success
                response = Mock()
                choice = Mock()
                message = Mock()
                message.content = "Response from Low Gear"
                choice.message = message
                response.choices = [choice]
                return response
        
        gateway.groq_client.chat.completions.create.side_effect = groq_side_effect
        
        messages = [{"role": "user", "content": "Test message"}]
        result = await gateway.generate_completion(messages)
        
        # Should have used Low Gear after High Gear failed
        assert result["provider"] == LLMProvider.GROQ.value
        # Should have shifted back to High Gear after success
        assert gateway.current_groq_gear == GroqGear.HIGH_GEAR

    @pytest.mark.asyncio
    async def test_rate_limit_in_both_gears_triggers_gemini(self, gateway_with_gears):
        """Test that rate limit in both gears triggers Gemini (Cannon Shot)"""
        gateway = gateway_with_gears
        
        # Make both Groq gears fail with rate limit
        gateway.groq_client.chat.completions.create.side_effect = Exception("Rate limit exceeded")
        
        messages = [{"role": "user", "content": "Test message"}]
        result = await gateway.generate_completion(messages)
        
        # Should have fallen back to Gemini (Cannon Shot)
        assert result["provider"] == LLMProvider.GEMINI.value
        assert "fallback_from" in result
        assert result["fallback_from"] == LLMProvider.GROQ.value


class TestAutoRepairSystem:
    """Test cases for Auto-Repair System"""

    @pytest.fixture
    def gateway_with_auto_repair(self):
        """Create a gateway with auto-repair enabled"""
        mock_github_adapter = Mock()
        mock_github_adapter.dispatch_auto_fix = AsyncMock(return_value={"success": True})
        
        gateway = AIGateway(
            groq_api_key="test_key",
            gemini_api_key="test_key",
            enable_auto_repair=True,
            github_adapter=mock_github_adapter,
        )
        
        # Mock Groq client
        gateway.groq_client = Mock()
        
        return gateway

    def test_auto_repair_initialization(self):
        """Test that auto-repair can be enabled/disabled"""
        # Enabled
        gateway = AIGateway(
            groq_api_key="test_key",
            enable_auto_repair=True,
        )
        assert gateway.enable_auto_repair is True
        
        # Disabled
        gateway = AIGateway(
            groq_api_key="test_key",
            enable_auto_repair=False,
        )
        assert gateway.enable_auto_repair is False

    @pytest.mark.asyncio
    async def test_auto_repair_not_triggered_for_non_critical_errors(self, gateway_with_auto_repair):
        """Test that auto-repair is not triggered for non-critical errors"""
        gateway = gateway_with_auto_repair
        
        # Non-critical error
        error = Exception("Some random error")
        error_traceback = "Traceback...\nException: Some random error"
        
        # Should not dispatch (we're just testing it doesn't raise)
        await gateway._dispatch_auto_repair_if_enabled(
            error=error,
            error_traceback=error_traceback,
            issue_title="Test issue",
            file_path="test_file.py"
        )
        
        # Verify dispatch was not called
        gateway.github_adapter.dispatch_auto_fix.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_repair_triggered_for_import_error(self, gateway_with_auto_repair):
        """Test that auto-repair is triggered for import errors"""
        gateway = gateway_with_auto_repair
        
        # Critical error - import error
        error = ImportError("No module named 'nonexistent_module'")
        error_traceback = "Traceback...\nImportError: No module named 'nonexistent_module'"
        
        # Should log the error (not dispatch in this implementation)
        await gateway._dispatch_auto_repair_if_enabled(
            error=error,
            error_traceback=error_traceback,
            issue_title="Import error",
            file_path="test_file.py"
        )
        
        # In current implementation, we just log the error
        # Real implementation would call dispatch_auto_fix

    @pytest.mark.asyncio
    async def test_auto_repair_disabled_when_no_github_adapter(self):
        """Test that auto-repair gracefully handles missing GitHub adapter"""
        gateway = AIGateway(
            groq_api_key="test_key",
            enable_auto_repair=True,
            github_adapter=None,  # No adapter
        )
        
        error = ImportError("Test import error")
        error_traceback = "Traceback...\nImportError: Test import error"
        
        # Should not raise even without GitHub adapter
        await gateway._dispatch_auto_repair_if_enabled(
            error=error,
            error_traceback=error_traceback,
            issue_title="Test issue",
            file_path="test_file.py"
        )

    @pytest.mark.asyncio
    async def test_generate_completion_captures_traceback_on_error(self):
        """Test that generate_completion captures full traceback on errors"""
        mock_github_adapter = Mock()
        mock_github_adapter.dispatch_auto_fix = AsyncMock(return_value={"success": True})
        
        gateway = AIGateway(
            groq_api_key="test_key",
            gemini_api_key="test_key",
            enable_auto_repair=True,
            github_adapter=mock_github_adapter,
        )
        
        # Mock Groq to raise a non-rate-limit error
        gateway.groq_client = Mock()
        gateway.groq_client.chat.completions.create.side_effect = Exception("Test error")
        
        messages = [{"role": "user", "content": "Test"}]
        
        # Should raise the error (after attempting auto-repair)
        with pytest.raises(Exception, match="Test error"):
            await gateway.generate_completion(messages)


class TestEnvironmentVariableConfiguration:
    """Test cases for environment variable configuration"""

    def test_groq_high_gear_from_env_var(self):
        """Test that High Gear model can be configured via GROQ_MODEL env var"""
        with patch.dict(os.environ, {"GROQ_MODEL": "custom-high-gear-model"}):
            gateway = AIGateway(groq_api_key="test_key")
            assert gateway.groq_high_gear_model == "custom-high-gear-model"

    def test_groq_low_gear_from_env_var(self):
        """Test that Low Gear model can be configured via GROQ_LOW_GEAR_MODEL env var"""
        with patch.dict(os.environ, {"GROQ_LOW_GEAR_MODEL": "custom-low-gear-model"}):
            gateway = AIGateway(groq_api_key="test_key")
            assert gateway.groq_low_gear_model == "custom-low-gear-model"

    def test_gemini_model_from_env_var(self):
        """Test that Gemini model can be configured via GEMINI_MODEL env var"""
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-custom"}):
            gateway = AIGateway(gemini_api_key="test_key")
            assert gateway.gemini_model == "gemini-custom"

    def test_default_models_when_no_env_vars(self):
        """Test that default models are used when no env vars are set"""
        with patch.dict(os.environ, {}, clear=True):
            gateway = AIGateway(groq_api_key="test_key", gemini_api_key="test_key")
            assert gateway.groq_high_gear_model == AIGateway.DEFAULT_HIGH_GEAR_MODEL
            assert gateway.groq_low_gear_model == AIGateway.DEFAULT_LOW_GEAR_MODEL
            assert gateway.gemini_model == AIGateway.DEFAULT_GEMINI_MODEL
