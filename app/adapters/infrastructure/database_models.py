# -*- coding: utf-8 -*-
"""Database models for user authentication using SQLModel"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """
    SQLModel table for storing user authentication data
    """

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, nullable=False, index=True)
    email: Optional[str] = Field(default=None, nullable=True)
    full_name: Optional[str] = Field(default=None, nullable=True)
    hashed_password: str = Field(nullable=False)
    disabled: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=datetime.now, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.now, nullable=False)
