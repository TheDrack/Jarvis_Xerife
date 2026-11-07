"""History context builders must request only the active user's records."""
from unittest.mock import Mock

import pytest

from app.adapters.infrastructure.gemini_response_helpers import build_context_message


@pytest.mark.parametrize(
    "user_id,expected",
    [
        ("alice", "alice private input"),
        ("bob", "bob private input"),
    ],
)
def test_gemini_context_requests_history_for_only_the_active_user(user_id, expected):
    provider = Mock()
    provider.get_recent_history.return_value = [
        {
            "user_input": expected,
            "command_type": "chat",
            "success": True,
        }
    ]

    context = build_context_message(provider, user_id=user_id)

    provider.get_recent_history.assert_called_once_with(limit=3, user_id=user_id)
    assert expected in context


def test_unscoped_gemini_context_requests_only_local_history():
    provider = Mock()
    provider.get_recent_history.return_value = [
        {"user_input": "local command", "command_type": "chat", "success": True}
    ]

    context = build_context_message(provider)

    provider.get_recent_history.assert_called_once_with(limit=3, user_id=None)
    assert "local command" in context
