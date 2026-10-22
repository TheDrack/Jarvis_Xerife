# -*- coding: utf-8 -*-
"""Domain models - Core business entities"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CommandType(Enum):
    """Types of commands the assistant can handle"""

    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    OPEN_BROWSER = "open_browser"
    OPEN_URL = "open_url"
    SEARCH_ON_PAGE = "search_on_page"
    OBSERVE_SCREEN = "observe_screen"
    WATCH_SCREEN = "watch_screen"
    RUN_VISUAL_RECIPE = "run_visual_recipe"
    CAPTURE_VISUAL_TEMPLATE = "capture_visual_template"
    SAVE_VISUAL_TEMPLATE = "save_visual_template"
    REPORT_ISSUE = "report_issue"
    RUN_WORKFLOW = "run_workflow"
    CHAT = "chat"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class Intent:
    """Represents the interpreted intent from user input"""

    command_type: CommandType
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""
    confidence: float = 1.0

    def __post_init__(self):
        """Validate intent after initialization"""
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")


@dataclass(slots=True)
class Command:
    """Represents a command to be executed"""

    intent: Intent
    timestamp: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Response:
    """Represents a response from command execution"""

    success: bool
    message: str = ""
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    def __post_init__(self):
        """Set default message based on success status"""
        if not self.message:
            self.message = "Command executed successfully" if self.success else "Command failed"
