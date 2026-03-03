# -*- coding: utf-8 -*-
"""Application services"""

from .assistant_service import AssistantService
from .browser_manager import PersistentBrowserManager
from .dependency_manager import DependencyManager
from .device_service import DeviceService
from .extension_manager import ExtensionManager
from .memory_manager import MemoryManager
from .task_runner import TaskRunner

__all__ = [
    "AssistantService",
    "DependencyManager",
    "ExtensionManager",
    "DeviceService",
    "MemoryManager",
    "TaskRunner",
    "PersistentBrowserManager",
]
