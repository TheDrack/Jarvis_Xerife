"""Append-only JSONL sink for secret-free tool execution events."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.runtime.toolbox.contracts import ToolExecutionEvent


class JsonlToolAuditSink:
    """Persist only the allowlisted metadata in ToolExecutionEvent."""

    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv(
            "JARVIS_TOOL_AUDIT_PATH", "data/tool_execution_audit.jsonl"
        )
        self.path = Path(configured)
        self._lock = threading.Lock()

    def __call__(self, event: ToolExecutionEvent) -> None:
        record = event.model_dump(mode="json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()

[executed on device: DESKTOP-HPJ82UA (d504f4a4-8a27-4cc9-94f5-7abc9b926b55)]