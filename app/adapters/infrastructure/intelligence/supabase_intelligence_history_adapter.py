"""Append-only Supabase persistence for normalized intelligence history."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.adapters.infrastructure.supabase_client import get_supabase_admin_client
from app.domain.intelligence.contracts import IntelligenceBatch

logger = logging.getLogger(__name__)

EVENT_TABLE = "intelligence_event_snapshots"
OBSERVATION_TABLE = "intelligence_observation_snapshots"


class SupabaseIntelligenceHistoryAdapter:
    """Persist and reload intelligence snapshots using server-only credentials.

    The adapter never falls back to the public/anon Supabase client. A missing
    service-role client is represented as an explicit unavailable state.
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client if client is not None else get_supabase_admin_client()

    @staticmethod
    def _canonical_hash(payload: dict[str, Any], *, observation: bool) -> str:
        semantic = dict(payload)
        semantic.pop("observed_at", None)
        evidence = semantic.get("evidence")
        if isinstance(evidence, dict):
            evidence = dict(evidence)
            evidence.pop("collected_at", None)
            semantic["evidence"] = evidence
        elif isinstance(evidence, list):
            semantic["evidence"] = [
                {key: value for key, value in item.items() if key != "collected_at"}
                if isinstance(item, dict) else item
                for item in evidence
            ]
        encoded = json.dumps(
            semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def persist_batch(self, batch: IntelligenceBatch) -> dict[str, Any]:
        """Idempotently append the semantic versions in a normalized batch."""
        if self._client is None:
            return {"status": "unavailable", "reason": "admin_client_not_configured",
                    "events_submitted": 0, "observations_submitted": 0}

        if not isinstance(batch, IntelligenceBatch):
            batch = IntelligenceBatch.model_validate(batch)

        event_rows = []
        for event in batch.events:
            payload = event.model_dump(mode="json")
            event_rows.append({
                "source_id": event.source_id,
                "event_id": event.event_id,
                "domain": event.domain,
                "category": event.category,
                "published_at": event.published_at.isoformat() if event.published_at else None,
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
                "observed_at": event.observed_at.isoformat(),
                "content_hash": self._canonical_hash(payload, observation=False),
                "payload": payload,
            })

        observation_rows = []
        for observation in batch.observations:
            payload = observation.model_dump(mode="json")
            observation_rows.append({
                "source_id": observation.source_id,
                "observation_id": observation.observation_id,
                "entity_type": observation.entity_type,
                "entity_id": observation.entity_id,
                "observed_at": observation.observed_at.isoformat(),
                "content_hash": self._canonical_hash(payload, observation=True),
                "payload": payload,
            })

        if event_rows:
            self._client.table(EVENT_TABLE).upsert(
                event_rows,
                on_conflict="source_id,event_id,content_hash",
                ignore_duplicates=True,
            ).execute()
        if observation_rows:
            self._client.table(OBSERVATION_TABLE).upsert(
                observation_rows,
                on_conflict="source_id,entity_type,entity_id,observed_at,content_hash",
                ignore_duplicates=True,
            ).execute()

        return {
            "status": "persisted",
            "events_submitted": len(event_rows),
            "observations_submitted": len(observation_rows),
        }

    def load_latest(self, limit: int = 100) -> dict[str, Any]:
        """Load recent event and observation payloads after process restarts."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit deve ser um inteiro entre 1 e 500.")
        if self._client is None:
            return {
                "events": [], "observations": [],
                "history_status": "unavailable",
                "history_reason": "admin_client_not_configured",
            }

        event_response = (
            self._client.table(EVENT_TABLE)
            .select("payload,observed_at")
            .order("observed_at", desc=True)
            .limit(limit)
            .execute()
        )
        observation_response = (
            self._client.table(OBSERVATION_TABLE)
            .select("payload,observed_at")
            .order("observed_at", desc=True)
            .limit(limit)
            .execute()
        )
        events = [
            row["payload"] for row in (event_response.data or [])
            if isinstance(row, dict) and isinstance(row.get("payload"), dict)
        ]
        observations = [
            row["payload"] for row in (observation_response.data or [])
            if isinstance(row, dict) and isinstance(row.get("payload"), dict)
        ]
        return {
            "events": events,
            "observations": observations,
            "history_status": "persisted",
            "history_reason": None,
        }
