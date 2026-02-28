#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Populate Jarvis Capabilities Database

This script loads capabilities from data/capabilities.json and populates
the jarvis_capabilities table in the database.

Usage:
    python migrations/populate_capabilities.py
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from sqlmodel import Session, select
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.domain.models.capability import JarvisCapability
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_capabilities_json(json_path: Path) -> List[Dict[str, Any]]:
    """Load capabilities from JSON file"""
    logger.info(f"Loading capabilities from {json_path}")
    with open(json_path, 'r') as f:
        capabilities = json.load(f)
    logger.info(f"Loaded {len(capabilities)} capabilities")
    return capabilities


def populate_capabilities(database_url: str = None):
    """
    Populate the jarvis_capabilities table with data from capabilities.json
    
    Args:
        database_url: Optional database URL override. If not provided, uses settings.database_url
    """
    # Initialize database adapter
    db_url = database_url or settings.database_url
    logger.info("Initializing database connection...")
    db_adapter = SQLiteHistoryAdapter(database_url=db_url)
    
    # Load capabilities from JSON
    json_path = Path(__file__).parent.parent / "data" / "capabilities.json"
    capabilities_data = load_capabilities_json(json_path)
    
    # Insert or update capabilities
    with Session(db_adapter.engine) as session:
        logger.info("Populating jarvis_capabilities table...")
        
        for cap_data in capabilities_data:
            # Check if capability already exists
            statement = select(JarvisCapability).where(JarvisCapability.id == cap_data["id"])
            existing = session.exec(statement).first()
            
            if existing:
                # Update existing capability
                logger.debug(f"Updating capability {cap_data['id']}: {cap_data['capability_name']}")
                existing.chapter = cap_data["chapter"]
                existing.capability_name = cap_data["capability_name"]
                # Don't override status if it's already been updated
                if existing.status == "nonexistent":
                    existing.status = cap_data["status"]
                # Don't override requirements/implementation_logic if they've been updated
                if not existing.requirements or existing.requirements == "[]":
                    existing.requirements = json.dumps(cap_data["requirements"])
                if not existing.implementation_logic:
                    existing.implementation_logic = cap_data["implementation_logic"]
            else:
                # Insert new capability
                logger.debug(f"Inserting capability {cap_data['id']}: {cap_data['capability_name']}")
                capability = JarvisCapability(
                    id=cap_data["id"],
                    chapter=cap_data["chapter"],
                    capability_name=cap_data["capability_name"],
                    status=cap_data["status"],
                    requirements=json.dumps(cap_data["requirements"]),
                    implementation_logic=cap_data["implementation_logic"]
                )
                session.add(capability)
        
        # Commit all changes
        session.commit()
        logger.info("✓ Successfully populated jarvis_capabilities table")
    
    # Verify the data
    with Session(db_adapter.engine) as session:
        count = session.exec(select(JarvisCapability)).all()
        logger.info(f"Total capabilities in database: {len(count)}")


if __name__ == "__main__":
    populate_capabilities()
