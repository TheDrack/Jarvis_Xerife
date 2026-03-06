from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Capability Detectors - Standalone functions for detecting JARVIS capability implementation status"""

import logging
from pathlib import Path
from typing import Dict

from sqlmodel import Session, select

from app.domain.models.capability import JarvisCapability

logger = logging.getLogger(__name__)


def detect_capability_inventory(engine) -> str:
    """Detect if capability #1 (internal inventory) is implemented"""
    # Check if we have the capabilities.json and database table
    json_path = Path(__file__).parent.parent.parent.parent / "data" / "capabilities.json"
    if json_path.exists():
        with Session(engine) as session:
            count = len(session.exec(select(JarvisCapability)).all())
            if count >= 102:
                return "complete"
            elif count > 0:
                return "partial"
    return "nonexistent"


def detect_capability_classification(engine) -> str:
    """Detect if capability #2 (classification by status) is implemented"""
    # Check if status field is being used
    with Session(engine) as session:
        capabilities = session.exec(select(JarvisCapability)).all()
        if len(capabilities) > 0:
            # Check if any capabilities have non-default status
            non_default = sum(1 for c in capabilities if c.status != "nonexistent")
            if non_default > 0:
                return "complete"
            else:
                return "partial"
    return "nonexistent"


def detect_existing_capabilities_recognition(detectors: Dict) -> str:
    """Detect if capability #16 (recognize existing capabilities) is implemented"""
    # Check if the CapabilityManager class exists and has detectors
    if len(detectors) > 0:
        return "partial"
    return "nonexistent"
