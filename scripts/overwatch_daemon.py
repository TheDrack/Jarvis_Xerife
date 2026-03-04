#!/usr/bin/env python
# -*- coding: utf-8 -*-
# DEPRECATED: Use app.adapters.infrastructure.overwatch_adapter.OverwatchDaemon
# Mantido para compatibilidade com scripts de análise externos.
# The canonical implementation now lives within the hexagonal architecture.

import sys
from pathlib import Path

# Ensure project root is importable when run directly
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.adapters.infrastructure.overwatch_adapter import OverwatchDaemon  # noqa: F401
