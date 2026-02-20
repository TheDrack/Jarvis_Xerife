import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


CAPABILITY_PATH = Path("docs/capabilities/capability.json")


class CapabilityRegistry:
    def __init__(self, path: Path = CAPABILITY_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Capability file not found: {path}")
        self.path = path
        self._capabilities = self._load()

    def _load(self) -> List[Dict]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._capabilities, f, indent=2, ensure_ascii=False)

    def all(self) -> List[Dict]:
        return self._capabilities

    def get_by_id(self, capability_id: int) -> Optional[Dict]:
        return next(
            (c for c in self._capabilities if c["id"] == capability_id),
            None
        )

    def get_next_unfulfilled(self, allowed_chapters: List[str] | None = None) -> Optional[Dict]:
        for c in self._capabilities:
            if c["status"] != "complete":
                if allowed_chapters and c["chapter"] not in allowed_chapters:
                    continue
                return c
        return None

    def mark_completed(
        self,
        capability_id: int,
        implementation_logic: str,
        requirements: List[str] | None = None,
        commit_hash: str | None = None
    ) -> bool:
        cap = self.get_by_id(capability_id)
        if not cap:
            return False

        cap["status"] = "complete"
        cap["implementation_logic"] = implementation_logic
        if requirements is not None:
            cap["requirements"] = requirements

        cap["completed_at"] = datetime.utcnow().isoformat()
        if commit_hash:
            cap["completed_by_commit"] = commit_hash

        self._save()
        return True