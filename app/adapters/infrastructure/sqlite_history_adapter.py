# -*- coding: utf-8 -*-
"""SQLite History Adapter - SQLModel implementation for command history persistence"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.application.ports.history_provider import HistoryProvider

logger = logging.getLogger(__name__)


class Interaction(SQLModel, table=True):
    """
    SQLModel table for storing command interactions
    """

    __tablename__ = "interactions"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.now, nullable=False)
    user_input: str = Field(nullable=False)
    command_type: str = Field(nullable=False)
    parameters: str = Field(default="{}", nullable=False)  # JSON string
    success: bool = Field(default=False, nullable=False)
    response_text: str = Field(default="", nullable=False)


class SQLiteHistoryAdapter(HistoryProvider):
    """
    SQLite implementation of the HistoryProvider port.
    Uses SQLModel for ORM and SQLite for storage.
    """

    def __init__(self, db_path: str = "jarvis.db"):
        """
        Initialize the SQLite history adapter

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        # Create SQLite engine
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        # Create tables
        SQLModel.metadata.create_all(self.engine)
        logger.info(f"Initialized SQLiteHistoryAdapter with database: {db_path}")

    def save_interaction(
        self,
        user_input: str,
        command_type: str,
        parameters: Dict[str, Any],
        success: bool,
        response_text: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Save a command interaction to the database

        Args:
            user_input: Raw user input
            command_type: Type of command executed
            parameters: Command parameters as dict
            success: Whether command succeeded
            response_text: Response message
            timestamp: Timestamp of the interaction (defaults to now)
        """
        try:
            with Session(self.engine) as session:
                interaction = Interaction(
                    timestamp=timestamp or datetime.now(),
                    user_input=user_input,
                    command_type=command_type,
                    parameters=json.dumps(parameters),
                    success=success,
                    response_text=response_text,
                )
                session.add(interaction)
                session.commit()
                logger.debug(f"Saved interaction: {user_input} -> {command_type}")
        except Exception as e:
            logger.error(f"Error saving interaction: {e}")

    def get_recent_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent command history

        Args:
            limit: Maximum number of commands to return

        Returns:
            List of command history items
        """
        try:
            with Session(self.engine) as session:
                statement = select(Interaction).order_by(Interaction.timestamp.desc()).limit(limit)
                results = session.exec(statement).all()

                history = []
                for interaction in results:
                    history.append(
                        {
                            "id": interaction.id,
                            "timestamp": interaction.timestamp.isoformat(),
                            "user_input": interaction.user_input,
                            "command_type": interaction.command_type,
                            "parameters": json.loads(interaction.parameters),
                            "success": interaction.success,
                            "response_text": interaction.response_text,
                        }
                    )
                return history
        except Exception as e:
            logger.error(f"Error getting recent history: {e}")
            return []

    def get_most_frequent_commands(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most frequently used commands using SQL aggregation

        Args:
            limit: Maximum number of commands to return

        Returns:
            List of command types with their frequency counts
        """
        try:
            with Session(self.engine) as session:
                # Use SQL aggregation to count command types
                statement = (
                    select(Interaction.command_type, func.count(Interaction.command_type).label("count"))
                    .group_by(Interaction.command_type)
                    .order_by(func.count(Interaction.command_type).desc())
                    .limit(limit)
                )
                results = session.exec(statement).all()

                frequency = []
                for command_type, count in results:
                    frequency.append({"command_type": command_type, "count": count})
                return frequency
        except Exception as e:
            logger.error(f"Error getting most frequent commands: {e}")
            return []

    def clear_history(self) -> None:
        """Clear all command history"""
        try:
            with Session(self.engine) as session:
                statement = select(Interaction)
                results = session.exec(statement)
                for interaction in results:
                    session.delete(interaction)
                session.commit()
                logger.info("Cleared all command history")
        except Exception as e:
            logger.error(f"Error clearing history: {e}")
