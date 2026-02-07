# -*- coding: utf-8 -*-
"""Database initialization utilities"""

import logging

from sqlmodel import SQLModel, create_engine

from app.adapters.infrastructure.auth_adapter import AuthAdapter
from app.adapters.infrastructure.database_models import User
from app.adapters.infrastructure.sqlite_history_adapter import Interaction
from app.core.config import settings

logger = logging.getLogger(__name__)


def initialize_database(database_url: str = None) -> None:
    """
    Initialize the database by creating all tables and ensuring default data exists.
    
    Args:
        database_url: Database connection URL. If None, uses settings.database_url
    """
    db_url = database_url or settings.database_url
    
    try:
        # Create engine
        engine = create_engine(db_url, echo=False)
        
        # Create all tables (imports User and Interaction models)
        logger.info("Creating database tables...")
        SQLModel.metadata.create_all(engine)
        logger.info("✓ Database tables created successfully")
        
        # Ensure default admin user exists
        auth_adapter = AuthAdapter(database_url=db_url)
        auth_adapter.ensure_default_admin()
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
