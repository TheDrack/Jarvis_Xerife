# -*- coding: utf-8 -*-
"""Database History Adapter - SQLModel implementation for command history persistence

Supports both SQLite (default/fallback) and PostgreSQL based on DATABASE_URL configuration.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, delete
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.application.ports.history_provider import HistoryProvider
from app.domain.models.device import Capability, Device
from app.domain.models.thought_log import ThoughtLog
from app.domain.models.capability import JarvisCapability

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
    status: str = Field(default="pending", nullable=False)  # pending, completed, failed
    processed_at: Optional[datetime] = Field(default=None, nullable=True)


class SQLiteHistoryAdapter(HistoryProvider):
    """
    Database implementation of the HistoryProvider port.
    Uses SQLModel for ORM and supports multiple database backends (SQLite, PostgreSQL, etc.).
    
    When database_url is provided (typically PostgreSQL from environment variables),
    uses that database. Otherwise, falls back to SQLite for local development/testing.
    
    Note: While the class is named SQLiteHistoryAdapter for backward compatibility,
    it supports any SQLAlchemy-compatible database URL.
    """

    def __init__(self, db_path: str = "jarvis.db", database_url: Optional[str] = None):
        """
        Initialize the database history adapter

        Args:
            db_path: Path to SQLite database file (used as fallback when database_url is None)
            database_url: Full database URL (e.g., postgresql://user:pass@host:port/db)
                         If provided, takes precedence over db_path.
                         Supports any SQLAlchemy-compatible URL (PostgreSQL, MySQL, etc.)
        """
        # Determine which database to use
        if database_url:
            # Normalize PostgreSQL URL for compatibility
            # Heroku/Render often provide postgres:// but SQLAlchemy expects postgresql://
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
                logger.info("Converted postgres:// URL to postgresql:// for SQLAlchemy compatibility")
            
            # Use psycopg2 driver explicitly for PostgreSQL if no driver is specified
            if database_url.startswith("postgresql://") and "+" not in database_url.split("://")[0]:
                database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
                logger.info("Using postgresql+psycopg2:// driver for PostgreSQL")
            
            self.database_url = database_url
            db_type = database_url.split(':')[0].split('+')[0]  # Extract base type (postgresql, mysql, etc.)
            logger.info(f"Using {db_type} database from DATABASE_URL")
        else:
            self.database_url = f"sqlite:///{db_path}"
            logger.info(f"Using SQLite database: {db_path}")
        
        # Create database engine
        self.engine = create_engine(self.database_url, echo=False)
        
        # Create tables
        SQLModel.metadata.create_all(self.engine)
        logger.info(f"Database tables initialized successfully")

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
                session.exec(delete(Interaction))
                session.commit()
                logger.info("Cleared all command history")
        except Exception as e:
            logger.error(f"Error clearing history: {e}")

    def save_pending_command(
        self,
        user_input: str,
        command_type: str,
        parameters: Dict[str, Any],
    ) -> Optional[int]:
        """
        Save a command with pending status to the database
        
        Args:
            user_input: Raw user input
            command_type: Type of command to execute
            parameters: Command parameters as dict
            
        Returns:
            ID of the created interaction, or None if failed
        """
        try:
            with Session(self.engine) as session:
                interaction = Interaction(
                    timestamp=datetime.now(),
                    user_input=user_input,
                    command_type=command_type,
                    parameters=json.dumps(parameters),
                    success=False,
                    response_text="",
                    status="pending",
                    processed_at=None,
                )
                session.add(interaction)
                session.commit()
                session.refresh(interaction)
                logger.info(f"Saved pending command with ID {interaction.id}: {user_input} -> {command_type}")
                return interaction.id
        except Exception as e:
            logger.error(f"Error saving pending command: {e}")
            return None

    def get_next_pending_command(self) -> Optional[Dict[str, Any]]:
        """
        Get the oldest pending command from the database
        
        Returns:
            Pending command dict or None if no pending commands
        """
        try:
            with Session(self.engine) as session:
                statement = (
                    select(Interaction)
                    .where(Interaction.status == "pending")
                    .order_by(Interaction.timestamp.asc())
                    .limit(1)
                )
                interaction = session.exec(statement).first()
                
                if interaction:
                    return {
                        "id": interaction.id,
                        "timestamp": interaction.timestamp.isoformat(),
                        "user_input": interaction.user_input,
                        "command_type": interaction.command_type,
                        "parameters": json.loads(interaction.parameters),
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting next pending command: {e}")
            return None

    def update_command_status(
        self,
        command_id: int,
        status: str,
        success: bool,
        response_text: str = "",
    ) -> bool:
        """
        Update the status of a command after processing
        
        Args:
            command_id: ID of the command to update
            status: New status (completed or failed)
            success: Whether the command succeeded
            response_text: Response message
            
        Returns:
            True if update succeeded, False otherwise
        """
        try:
            with Session(self.engine) as session:
                statement = select(Interaction).where(Interaction.id == command_id)
                interaction = session.exec(statement).first()
                
                if interaction:
                    interaction.status = status
                    interaction.success = success
                    interaction.response_text = response_text
                    interaction.processed_at = datetime.now()
                    session.add(interaction)
                    session.commit()
                    logger.info(f"Updated command {command_id} status to {status}")
                    return True
                else:
                    logger.warning(f"Command {command_id} not found")
                    return False
        except Exception as e:
            logger.error(f"Error updating command status: {e}")
            return False
