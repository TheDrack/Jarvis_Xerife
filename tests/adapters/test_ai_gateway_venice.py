"""Regression tests for optional Venice integration in AIGateway."""
from unittest.mock import Mock

import pytest

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider


def make_gateway():
    return AIGateway(
        groq_api_key=None,
        gemini_api_key=None,
        venice_api_key=None,
        enable_auto_repair=False,
    )


def test_venice_is_optional_and_does_not_change_existing_default():
    gateway = make_gateway()
    gateway.groq_client = Mock()
    gateway.gemini_client = Mock()
    gateway.venice_client = Mock()

    assert gateway.default_provider == LLMProvider.GROQ
    assert gateway.select_provider("short request") == LLMProvider.GROQ


def test_venice_is_selected_when_it_is_the_only_available_provider():
    gateway = make_gateway()
    gateway.venice_client = Mock()

    assert gateway.select_provider("short request") == LLMProvider.VENICE


def test_force_provider_can_select_venice():
    gateway = make_gateway()
    gateway.groq_client = Mock()
    gateway.venice_client = Mock()

    assert gateway.select_provider(
        "short request", force_provider=LLMProvider.VENICE
    ) == LLMProvider.VENICE


def test_multimodal_selection_uses_venice_when_gemini_is_unavailable():
    gateway = make_gateway()
    gateway.venice_client = Mock()

    assert gateway.select_provider("image analysis", multimodal=True) == LLMProvider.VENICE


@pytest.mark.anyio
async def test_generate_completion_uses_venice_openai_compatible_client():
    gateway = make_gateway()
    gateway.venice_client = Mock()
    completion = Mock()
    completion.choices[0].message.content = "Venice response"
    gateway.venice_client.chat.completions.create.return_value = completion

    result = await gateway.generate_completion(
        [{"role": "user", "content": "Hello"}],
        force_provider=LLMProvider.VENICE,
    )

    assert result["provider"] == "venice"
    assert result["model"] == "venice-uncensored-1-2"
    assert result["response"] is completion
    gateway.venice_client.chat.completions.create.assert_called_once_with(
        model="venice-uncensored-1-2",
        messages=[{"role": "user", "content": "Hello"}],
    )
