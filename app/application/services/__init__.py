# -*- coding: utf-8 -*-
"""Application services

Each service import is guarded so that missing optional dependencies
(e.g. ``sqlmodel``) do not prevent this package from being loaded in
minimal environments such as the self-healing workflow, where only a
subset of packages is installed (pytest, groq, requests, autopep8…).

When an optional service is unavailable its name is set to ``None``.
Callers that need a specific service should check::

    from app.application.services import AssistantService
    if AssistantService is None:
        raise RuntimeError("AssistantService requires sqlmodel to be installed")
"""

# Guard each import so that missing optional dependencies (e.g. sqlmodel) do not
# prevent the package from being imported in minimal environments such as the
# self-healing workflow, where only a subset of packages is installed.
try:
    from .assistant_service import AssistantService
except ImportError:
    AssistantService = None  # type: ignore[assignment,misc]

try:
    from .browser_manager import PersistentBrowserManager
except ImportError:
    PersistentBrowserManager = None  # type: ignore[assignment,misc]

try:
    from .dependency_manager import DependencyManager
except ImportError:
    DependencyManager = None  # type: ignore[assignment,misc]

try:
    from .device_service import DeviceService
except ImportError:
    DeviceService = None  # type: ignore[assignment,misc]

try:
    from .extension_manager import ExtensionManager
except ImportError:
    ExtensionManager = None  # type: ignore[assignment,misc]

try:
    from .memory_manager import MemoryManager
except ImportError:
    MemoryManager = None  # type: ignore[assignment,misc]

try:
    from .task_runner import TaskRunner
except ImportError:
    TaskRunner = None  # type: ignore[assignment,misc]

__all__ = [
    "AssistantService",
    "DependencyManager",
    "ExtensionManager",
    "DeviceService",
    "MemoryManager",
    "TaskRunner",
    "PersistentBrowserManager",
]
