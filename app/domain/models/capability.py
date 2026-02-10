# -*- coding: utf-8 -*-
"""JARVIS Capability Model for Self-Awareness Module"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class JarvisCapability(SQLModel, table=True):
    """
    SQLModel table for storing JARVIS self-awareness capabilities.
    
    This table tracks the 102 capabilities defined in JARVIS_OBJECTIVES_MAP,
    organized across 9 chapters from basic foundation to Marvel-level AI.
    
    Each capability has a status (nonexistent, partial, complete) and tracks
    the requirements and implementation logic needed to achieve it.
    """

    __tablename__ = "jarvis_capabilities"

    id: int = Field(primary_key=True)  # Capability ID from JARVIS_OBJECTIVES_MAP
    chapter: str = Field(nullable=False, index=True)  # e.g., "CHAPTER_1_IMMEDIATE_FOUNDATION"
    capability_name: str = Field(nullable=False)  # Human-readable capability description
    status: str = Field(default="nonexistent", nullable=False, index=True)  # nonexistent, partial, complete
    requirements: str = Field(default="[]", nullable=False)  # JSON array of technical requirements
    implementation_logic: str = Field(default="", nullable=False)  # How the capability is/should be implemented
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=False)
