from app.core.nexuscomponent import NexusComponent
# -*- coding: utf-8 -*-
"""Tests for SQLite History Adapter"""

from datetime import datetime

import pytest

from app.adapters.infrastructure.sqlite_history_adapter import (
    Interaction,
    SQLiteHistoryAdapter,
)


class TestSQLiteHistoryAdapter(NexusComponent):

    def execute(self, context: dict):
        """Execução automática JARVIS."""
        pass
    """Test cases for SQLiteHistoryAdapter"""

    @pytest.fixture
    def adapter(self):
        """Create an adapter instance with in-memory database"""
        return SQLiteHistoryAdapter(database_url="sqlite:///:memory:")

    def test_initialization(self):
        """Test adapter initialization creates database and tables"""
        adapter = SQLiteHistoryAdapter(database_url="sqlite:///:memory:")
        assert adapter.database_url == "sqlite:///:memory:"

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

    def test_save_pending_command(self, adapter):
        """Test saving a pending command for distributed mode"""
        task_id = adapter.save_pending_command(
            user_input="digite teste",
            command_type="type_text",
            parameters={"text": "teste"},
        )

        # Verify task ID was returned
        assert task_id is not None
        assert isinstance(task_id, int)

        # Verify it was saved with pending status
        history = adapter.get_recent_history(limit=1)
        assert len(history) == 1
        assert history[0]["user_input"] == "digite teste"
        assert history[0]["command_type"] == "type_text"

    def test_get_next_pending_command(self, adapter):
        """Test getting the next pending command"""
        # Save a pending command
        task_id = adapter.save_pending_command(
            user_input="comando pendente",
            command_type="test_type",
            parameters={"key": "value"},
        )

        # Get the next pending command
        pending = adapter.get_next_pending_command()
        assert pending is not None
        assert pending["id"] == task_id
        assert pending["user_input"] == "comando pendente"
        assert pending["command_type"] == "test_type"
        assert pending["parameters"] == {"key": "value"}

    def test_get_next_pending_command_empty(self, adapter):
        """Test getting pending command when none exist"""
        pending = adapter.get_next_pending_command()
        assert pending is None

    def test_get_next_pending_command_oldest_first(self, adapter):
        """Test that oldest pending command is returned first"""
        # Save multiple pending commands with explicit timestamps
        from datetime import datetime, timedelta
        
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        
        # Create first command with earlier timestamp
        task_id_1 = adapter.save_pending_command(
            user_input="comando 1",
            command_type="test_type",
            parameters={},
        )
        # Manually update timestamp to be earlier
        from sqlmodel import Session, select
        with Session(adapter.engine) as session:
            from app.adapters.infrastructure.sqlite_history_adapter import Interaction
            stmt = select(Interaction).where(Interaction.id == task_id_1)
            interaction = session.exec(stmt).first()
            if interaction:
                interaction.timestamp = base_time
                session.add(interaction)
                session.commit()
        
        # Create second command with later timestamp
        task_id_2 = adapter.save_pending_command(
            user_input="comando 2",
            command_type="test_type",
            parameters={},
        )
        # Manually update timestamp to be later
        with Session(adapter.engine) as session:
            stmt = select(Interaction).where(Interaction.id == task_id_2)
            interaction = session.exec(stmt).first()
            if interaction:
                interaction.timestamp = base_time + timedelta(seconds=1)
                session.add(interaction)
                session.commit()

        # Get next pending - should be the oldest one
        pending = adapter.get_next_pending_command()
        assert pending is not None
        assert pending["id"] == task_id_1
        assert pending["user_input"] == "comando 1"

    def test_update_command_status_to_completed(self, adapter):
        """Test updating command status to completed"""
        # Save a pending command
        task_id = adapter.save_pending_command(
            user_input="comando teste",
            command_type="test_type",
            parameters={},
        )

        # Update to completed
        result = adapter.update_command_status(
            command_id=task_id,
            status="completed",
            success=True,
            response_text="Comando executado com sucesso",
        )

        assert result is True

        # Verify the update
        history = adapter.get_recent_history(limit=1)
        assert len(history) == 1
        # Note: get_recent_history doesn't return status/processed_at
        # We could verify by directly querying if needed

    def test_update_command_status_to_failed(self, adapter):
        """Test updating command status to failed"""
        # Save a pending command
        task_id = adapter.save_pending_command(
            user_input="comando teste",
            command_type="test_type",
            parameters={},
        )

        # Update to failed
        result = adapter.update_command_status(
            command_id=task_id,
            status="failed",
            success=False,
            response_text="Erro ao executar comando",
        )

        assert result is True

    def test_update_command_status_nonexistent(self, adapter):
        """Test updating status of non-existent command"""
        result = adapter.update_command_status(
            command_id=99999,
            status="completed",
            success=True,
            response_text="Test",
        )

        assert result is False

    def test_pending_commands_not_returned_after_completion(self, adapter):
        """Test that completed commands are not returned as pending"""
        # Save a pending command
        task_id = adapter.save_pending_command(
            user_input="comando teste",
            command_type="test_type",
            parameters={},
        )

        # Verify it's pending
        pending = adapter.get_next_pending_command()
        assert pending is not None
        assert pending["id"] == task_id

        # Mark as completed
        adapter.update_command_status(
            command_id=task_id,
            status="completed",
            success=True,
            response_text="Done",
        )

        # Verify it's no longer pending
        pending = adapter.get_next_pending_command()
        assert pending is None

