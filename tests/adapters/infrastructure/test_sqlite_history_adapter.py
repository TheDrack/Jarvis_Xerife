# -*- coding: utf-8 -*-
"""Tests for SQLite History Adapter"""

import os
import tempfile
from datetime import datetime

import pytest

from app.adapters.infrastructure.sqlite_history_adapter import (
    Interaction,
    SQLiteHistoryAdapter,
)


class TestSQLiteHistoryAdapter:
    """Test cases for SQLiteHistoryAdapter"""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        # Cleanup
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def adapter(self, temp_db):
        """Create an adapter instance with temporary database"""
        return SQLiteHistoryAdapter(db_path=temp_db)

    def test_initialization(self, temp_db):
        """Test adapter initialization creates database and tables"""
        adapter = SQLiteHistoryAdapter(db_path=temp_db)
        assert adapter.db_path == temp_db
        assert os.path.exists(temp_db)

    def test_save_interaction(self, adapter):
        """Test saving an interaction to the database"""
        adapter.save_interaction(
            user_input="digite olá",
            command_type="type_text",
            parameters={"text": "olá"},
            success=True,
            response_text="Typed: olá",
        )

        # Verify it was saved
        history = adapter.get_recent_history(limit=1)
        assert len(history) == 1
        assert history[0]["user_input"] == "digite olá"
        assert history[0]["command_type"] == "type_text"
        assert history[0]["parameters"] == {"text": "olá"}
        assert history[0]["success"] is True
        assert history[0]["response_text"] == "Typed: olá"

    def test_save_interaction_with_timestamp(self, adapter):
        """Test saving an interaction with a specific timestamp"""
        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        adapter.save_interaction(
            user_input="test command",
            command_type="test_type",
            parameters={},
            success=True,
            response_text="Test response",
            timestamp=timestamp,
        )

        history = adapter.get_recent_history(limit=1)
        assert len(history) == 1
        # The timestamp should be in ISO format
        assert history[0]["timestamp"].startswith("2024-01-01")

    def test_get_recent_history(self, adapter):
        """Test getting recent command history"""
        # Add multiple interactions
        for i in range(5):
            adapter.save_interaction(
                user_input=f"command {i}",
                command_type="test_type",
                parameters={"index": i},
                success=True,
                response_text=f"Response {i}",
            )

        # Get recent history (default limit)
        history = adapter.get_recent_history(limit=3)
        assert len(history) == 3
        # Should be in reverse chronological order (most recent first)
        assert history[0]["user_input"] == "command 4"
        assert history[1]["user_input"] == "command 3"
        assert history[2]["user_input"] == "command 2"

    def test_get_recent_history_empty(self, adapter):
        """Test getting history when database is empty"""
        history = adapter.get_recent_history()
        assert history == []

    def test_get_most_frequent_commands(self, adapter):
        """Test getting most frequent commands using SQL aggregation"""
        # Add interactions with different command types
        adapter.save_interaction(
            user_input="digite texto1",
            command_type="type_text",
            parameters={},
            success=True,
            response_text="Typed",
        )
        adapter.save_interaction(
            user_input="digite texto2",
            command_type="type_text",
            parameters={},
            success=True,
            response_text="Typed",
        )
        adapter.save_interaction(
            user_input="digite texto3",
            command_type="type_text",
            parameters={},
            success=True,
            response_text="Typed",
        )
        adapter.save_interaction(
            user_input="pressione enter",
            command_type="press_key",
            parameters={},
            success=True,
            response_text="Pressed",
        )
        adapter.save_interaction(
            user_input="pressione enter",
            command_type="press_key",
            parameters={},
            success=True,
            response_text="Pressed",
        )
        adapter.save_interaction(
            user_input="abrir navegador",
            command_type="open_browser",
            parameters={},
            success=True,
            response_text="Opened",
        )

        # Get most frequent commands
        frequency = adapter.get_most_frequent_commands(limit=10)
        assert len(frequency) == 3
        # Should be sorted by count (descending)
        assert frequency[0]["command_type"] == "type_text"
        assert frequency[0]["count"] == 3
        assert frequency[1]["command_type"] == "press_key"
        assert frequency[1]["count"] == 2
        assert frequency[2]["command_type"] == "open_browser"
        assert frequency[2]["count"] == 1

    def test_get_most_frequent_commands_with_limit(self, adapter):
        """Test getting most frequent commands with a limit"""
        # Add interactions
        for i in range(5):
            adapter.save_interaction(
                user_input=f"command {i}",
                command_type=f"type_{i}",
                parameters={},
                success=True,
                response_text="Response",
            )

        frequency = adapter.get_most_frequent_commands(limit=3)
        assert len(frequency) == 3

    def test_get_most_frequent_commands_empty(self, adapter):
        """Test getting most frequent commands when database is empty"""
        frequency = adapter.get_most_frequent_commands()
        assert frequency == []

    def test_clear_history(self, adapter):
        """Test clearing all command history"""
        # Add some interactions
        for i in range(3):
            adapter.save_interaction(
                user_input=f"command {i}",
                command_type="test_type",
                parameters={},
                success=True,
                response_text="Response",
            )

        # Verify they exist
        history = adapter.get_recent_history()
        assert len(history) == 3

        # Clear history
        adapter.clear_history()

        # Verify history is empty
        history = adapter.get_recent_history()
        assert len(history) == 0

    def test_save_interaction_with_complex_parameters(self, adapter):
        """Test saving interaction with complex JSON parameters"""
        complex_params = {
            "text": "hello world",
            "nested": {"key": "value", "list": [1, 2, 3]},
            "number": 42,
        }

        adapter.save_interaction(
            user_input="complex command",
            command_type="test_type",
            parameters=complex_params,
            success=True,
            response_text="Response",
        )

        history = adapter.get_recent_history(limit=1)
        assert len(history) == 1
        assert history[0]["parameters"] == complex_params
