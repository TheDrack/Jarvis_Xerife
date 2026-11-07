"""Service-role backed persistence for user-partitioned vector memories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional

from app.adapters.infrastructure.supabase_client import get_supabase_admin_client

logger = logging.getLogger(__name__)

_TABLE_NAME = "jarvis_vector_memories"
_PAGE_SIZE = 1000


class SupabaseVectorMemoryStore:
    """Persist semantic-memory records in Supabase with an authoritative scope key.

    The adapter accepts only a trusted `user_id` already placed on the event by
    VectorMemoryAdapter. That value is copied into a dedicated database column;
    it is never trusted from the metadata JSON object.
    """

    def __init__(self, client: Any = None, table_name: str = _TABLE_NAME) -> None:
        self._client = client if client is not None else get_supabase_admin_client()
        self._table_name = table_name

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def is_healthy(self) -> bool:
        if not self.is_available:
            return False
        try:
            self._client.table(self._table_name).select("id").limit(1).execute()
            return True
        except Exception:
            logger.warning("Supabase vector-memory health check failed", exc_info=True)
            return False

    @staticmethod
    def _scope_key(user_id: Optional[str]) -> str:
        if user_id is None:
            return "system"
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-empty string when provided")
        return f"user:{user_id.strip()}"

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("vector-memory timestamp must be datetime or ISO string")
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def append(
        self,
        event: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> None:
        if not self.is_available:
            raise RuntimeError("Supabase vector-memory persistence is unavailable")

        metadata = dict(event.get("metadata") or {})
        metadata_user_id = metadata.pop("user_id", None)
        if user_id is None:
            if metadata_user_id is not None:
                raise ValueError(
                    "user_id must be supplied as a trusted user_id argument"
                )
        else:
            if not isinstance(user_id, str) or not user_id.strip():
                raise ValueError("user_id must be a non-empty string when provided")
            user_id = user_id.strip()
            if metadata_user_id is not None and metadata_user_id != user_id:
                raise ValueError("metadata user_id conflicts with trusted user_id")
        vector = event.get("vector")
        if not isinstance(vector, list) or not vector:
            raise ValueError("vector-memory embedding must be a non-empty list")
        normalized_vector = [float(value) for value in vector]
        row = {
            "id": str(event["id"]),
            "user_id": user_id,
            "scope_key": self._scope_key(user_id),
            "event_text": str(event["text"]),
            "embedding": normalized_vector,
            "metadata": metadata,
            "vector_dim": len(normalized_vector),
            "created_at": self._timestamp(event.get("timestamp")).isoformat(),
        }
        self._client.table(self._table_name).insert(row).execute()

    def list_events(
        self,
        user_id: Optional[str] = None,
        days_back: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_available:
            raise RuntimeError("Supabase vector-memory persistence is unavailable")
        if days_back is not None and (not isinstance(days_back, int) or days_back < 0):
            raise ValueError("days_back must be a non-negative integer or None")

        scope_key = self._scope_key(user_id)
        cutoff = (
            (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
            if days_back is not None
            else None
        )
        events: List[Dict[str, Any]] = []
        offset = 0
        while True:
            query = (
                self._client.table(self._table_name)
                .select("id,user_id,scope_key,event_text,embedding,metadata,created_at,vector_dim")
                .eq("scope_key", scope_key)
                .order("created_at", desc=True)
                .range(offset, offset + _PAGE_SIZE - 1)
            )
            if cutoff is not None:
                query = query.gte("created_at", cutoff)
            response = query.execute()
            rows = response.data or []
            for row in rows:
                metadata = dict(row.get("metadata") or {})
                # The database column is authoritative; JSON metadata cannot
                # select or override the owner partition.
                metadata.pop("user_id", None)
                if row.get("user_id") is not None:
                    metadata["user_id"] = row["user_id"]
                events.append(
                    {
                        "id": str(row["id"]),
                        "text": row["event_text"],
                        "vector": [float(value) for value in row["embedding"]],
                        "metadata": metadata,
                        "timestamp": self._timestamp(row["created_at"]).isoformat(),
                    }
                )
            if len(rows) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        return events

    def delete_events(self, user_id: Optional[str] = None) -> None:
        if not self.is_available:
            raise RuntimeError("Supabase vector-memory persistence is unavailable")
        scope_key = self._scope_key(user_id)
        self._client.table(self._table_name).delete().eq("scope_key", scope_key).execute()

    def delete_all(self) -> None:
        """Delete every partition; called only by the explicit adapter clear()."""
        if not self.is_available:
            raise RuntimeError("Supabase vector-memory persistence is unavailable")
        # scope_key is constrained to non-empty values by the table check.
        self._client.table(self._table_name).delete().neq("scope_key", "").execute()
