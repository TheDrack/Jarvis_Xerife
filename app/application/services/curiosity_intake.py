"""Capture discoveries as curiosity cards without mutating the codebase."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.nexus import NexusComponent


_DEFAULT_STORE = Path("data/curiosity/inbox.jsonl")
_MAX_TEXT = 4000
_SOURCE_TYPES = {"research", "news", "paper", "conversation", "idea", "error", "tool", "metric", "other"}


class CuriosityIntake(NexusComponent):
    """Nexus component that records evidence-aware discovery cards.

    This component is deliberately observational: it never executes source
    material, changes application code, installs dependencies, or triggers
    auto-evolution. Promotion to an experiment is a separate reviewed step.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        super().__init__()
        self.storage_path = Path(storage_path) if storage_path else _DEFAULT_STORE

    def configure(self, config: Dict[str, Any]) -> None:
        path = config.get("storage_path")
        if path:
            self.storage_path = Path(str(path))

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        action = str(ctx.get("action", "capture"))
        if action == "list_recent":
            limit = max(1, min(int(ctx.get("limit", 20)), 100))
            records = self._read_records()
            return {"success": True, "records": records[-limit:], "total": len(records)}
        if action != "capture":
            return {"success": False, "error": f"Unsupported curiosity action: {action}"}
        return self._capture(ctx)

    def _capture(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        title = self._text(ctx.get("source_title") or ctx.get("title"), 300)
        observation = self._text(ctx.get("observation") or ctx.get("summary"), _MAX_TEXT)
        source_uri = self._text(ctx.get("source_uri") or ctx.get("url"), 1000)
        if not title and not observation:
            return {"success": False, "error": "source_title or observation is required"}

        source_type = str(ctx.get("source_type", "other")).strip().lower()
        if source_type not in _SOURCE_TYPES:
            source_type = "other"

        identity = "\n".join((source_type, source_uri.casefold(), title.casefold(), observation.casefold()))
        record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
        existing = self._read_records()
        for record in existing:
            if record.get("id") == record_id:
                return {"success": True, "duplicate": True, "record": record}

        record = {
            "id": record_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_type": source_type,
            "source_uri": source_uri or None,
            "source_title": title or None,
            "observation": observation,
            "evidence_level": self._evidence_level(ctx.get("evidence_level", "unverified")),
            "user_benefit": self._text(ctx.get("user_benefit"), 1000) or None,
            "jarvis_benefit": self._text(ctx.get("jarvis_benefit"), 1000) or None,
            "connections": self._string_list(ctx.get("connections")),
            "open_questions": self._string_list(ctx.get("open_questions")) or [
                "What primary source verifies this claim?",
                "Which concrete user problem or Jarvis limitation could it improve?",
                "What already exists that could be reused?",
                "What small, reversible experiment could validate the idea?",
            ],
            "experiment": self._text(ctx.get("experiment"), 1000) or None,
            "risks": self._string_list(ctx.get("risks")),
            "priority": self._priority(ctx.get("priority")),
            "status": "captured",
            "next_action": self._text(ctx.get("next_action"), 500) or "Investigate sources, relevance, existing implementations, and a measurable low-risk test.",
        }

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return {"success": True, "duplicate": False, "record": record}

    def _read_records(self) -> list[Dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        records = []
        with self.storage_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(value, dict):
                    records.append(value)
        return records

    @staticmethod
    def _text(value: Any, limit: int) -> str:
        if not isinstance(value, str):
            return ""
        text = value.strip()[:limit]
        # Best-effort redaction of common credential formats before persistence.
        patterns = (
            (r"(?i)\b(?:ghp|github_pat|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{10,}\b", "[REDACTED_TOKEN]"),
            (r"(?i)\bsk-[A-Za-z0-9_-]{16,}\b", "[REDACTED_API_KEY]"),
            (r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", "Bearer [REDACTED_TOKEN]"),
            (r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]"),
        )
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text)
        return text

    @staticmethod
    def _evidence_level(value: Any) -> str:
        allowed = {"unverified", "reported", "documented", "replicated", "validated"}
        normalized = str(value).strip().lower()
        return normalized if normalized in allowed else "unverified"

    @staticmethod
    def _priority(value: Any) -> Dict[str, str]:
        default = {"impact": "unknown", "effort": "unknown", "confidence": "low"}
        if not isinstance(value, dict):
            return default
        allowed = ("impact", "effort", "confidence", "urgency")
        return {key: str(value.get(key, default.get(key, "unknown")))[:40] for key in allowed}

    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        result = []
        for item in value[:30]:
            normalized = cls._text(item, 500)
            if normalized:
                result.append(normalized)
        return result
