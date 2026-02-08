# -*- coding: utf-8 -*-
"""Application services"""

from .assistant_service import AssistantService
from .browser_manager import PersistentBrowserManager
from .dependency_manager import DependencyManager
from .device_service import DeviceService
from .extension_manager import ExtensionManager
from .task_runner import TaskRunner

__all__ = [
    "AssistantService",
    "DependencyManager",
    "ExtensionManager",
    "DeviceService",
    "TaskRunner",
    "PersistentBrowserManager",
]
