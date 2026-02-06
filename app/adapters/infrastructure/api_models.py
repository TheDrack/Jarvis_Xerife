# -*- coding: utf-8 -*-
"""Pydantic models for API request/response validation"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    """Request model for command execution"""

    command: str = Field(..., description="Command to execute", min_length=1)


class ExecuteResponse(BaseModel):
    """Response model for command execution"""

    success: bool = Field(..., description="Whether the command executed successfully")
    message: str = Field(..., description="Result message")
    data: Optional[Dict[str, Any]] = Field(None, description="Optional response data")
    error: Optional[str] = Field(None, description="Error code if execution failed")


class StatusResponse(BaseModel):
    """Response model for system status"""

    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    is_active: bool = Field(..., description="Whether the AI is active")
    wake_word: str = Field(..., description="Wake word for the assistant")
    language: str = Field(..., description="Language for voice recognition")


class CommandHistoryItem(BaseModel):
    """Single command history item"""

    command: str = Field(..., description="Command that was executed")
    timestamp: str = Field(..., description="ISO timestamp of execution")
    success: bool = Field(..., description="Whether the command succeeded")
    message: str = Field(..., description="Result message")


class HistoryResponse(BaseModel):
    """Response model for command history"""

    commands: List[CommandHistoryItem] = Field(..., description="List of recent commands")
    total: int = Field(..., description="Total number of commands in history")


# Authentication Models


class Token(BaseModel):
    """OAuth2 token response"""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(..., description="Token type (bearer)")


class TokenData(BaseModel):
    """Data encoded in JWT token"""

    username: Optional[str] = Field(None, description="Username from token")


class User(BaseModel):
    """User model"""

    username: str = Field(..., description="Username")
    email: Optional[str] = Field(None, description="User email")
    full_name: Optional[str] = Field(None, description="User full name")
    disabled: Optional[bool] = Field(None, description="Whether user is disabled")

