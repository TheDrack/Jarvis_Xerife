"""Server-side, append-only Supabase persistence for Universal Intelligence."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from app.application.ports.intelligence_history_repository import (
    IntelligenceHistoryRepository,
)
from app.domain.intelligence.contracts import (
    IntelligenceEvent,
    IntelligenceObservation,
    IntelligenceReport,
)


EVENT_TABLE = "intelligence_event_snapshots"
OBSERVATION_TABLE = "intelligence_observation_snapshots"
EVENT_CONFLICT_COLUMNS = "source_id,event_id,content_hash"
OBSERVATION_CONFLICT_COLUMNS = (
    "source_id,entity_type,entity_id,observed_at,content_hash"
)


class IntelligenceHistoryPersistenceError(RuntimeError):
    """Sanitized persistence failure that does not include request credentials."""


class SupabaseIntelligenceHistoryAdapter(IntelligenceHistoryRepository):
    """Persist immutable intelligence snapshots through a trusted server client.

    The adapter never creates a public/anon client and never performs UPDATE or
    DELETE operations. Duplicate rows are ignored by the database unique
    constraints. If a multi-table or multi-chunk write partially succeeds, the
    caller may safely replay the complete report because every insert is
    idempotent.

    Construction with an injected client is intended for dependency injection
    and tests. Production composition must use from_server_admin_client().
    """

    def __init__(self, client: Any, *, batch_size: int = 100) -> None:
        if client is None:
            raise ValueError("Supabase server admin client is required")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size must be an integer")
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        self._client = client
        self._batch_size = batch_size

    @classmethod
    def from_server_admin_client(
        cls, *, batch_size: int = 100
    ) -> "SupabaseIntelligenceHistoryAdapter":
        """Build only from the existing service-role-only server factory.

        There is deliberately no fallback to the public Supabase client.
        Missing service-role configuration is fail-closed.
        """
        try:
            from app.adapters.infrastructure.supabase_client import (
                get_supabase_admin_client,
            )

            client = get_supabase_admin_client()
        except Exception:
            raise RuntimeError(
                "Supabase server admin client is unavailable"
            ) from None
        if client is None:
            raise RuntimeError(
                "Supabase server admin client is unavailable"
            )
        return cls(client, batch_size=batch_size)

    def persist(self, report: IntelligenceReport) -> None:
        """Append event and observation snapshots using conflict-safe upserts."""
        if not isinstance(report, IntelligenceReport):
            raise TypeError("report must be an IntelligenceReport")

        event_rows = [self._event_row(event) for event in report.events]
        observation_rows = [
            self._observation_row(observation)
            for observation in report.observations
        ]

        self._upsert_batches(
            EVENT_TABLE,
            event_rows,
            EVENT_CONFLICT_COLUMNS,
        )
        self._upsert_batches(
            OBSERVATION_TABLE,
            observation_rows,
            OBSERVATION_CONFLICT_COLUMNS,
        )

    def _upsert_batches(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        conflict_columns: str,
    ) -> None:
        for offset in range(0, len(rows), self._batch_size):
            batch = rows[offset : offset + self._batch_size]
            try:
                response = (
                    self._client.table(table_name)
                    .upsert(
                        batch,
                        on_conflict=conflict_columns,
                        ignore_duplicates=True,
                    )
                    .execute()
                )
            except Exception as exc:
                raise IntelligenceHistoryPersistenceError(
                    f"{table_name} upsert failed ({type(exc).__name__})"
                ) from None

            if getattr(response, "error", None) is not None:
                raise IntelligenceHistoryPersistenceError(
                    f"{table_name} upsert returned an error"
                )

    @classmethod
    def _event_row(cls, event: IntelligenceEvent) -> dict[str, Any]:
        payload = event.model_dump(mode="json")
        semantic_payload = copy.deepcopy(payload)
        semantic_payload.pop("observed_at", None)
        evidence = semantic_payload.get("evidence")
        if isinstance(evidence, dict):
            evidence.pop("collected_at", None)

        return {
            "source_id": event.source_id,
            "event_id": event.event_id,
            "domain": event.domain,
            "category": event.category,
            "published_at": payload.get("published_at"),
            "occurred_at": payload.get("occurred_at"),
            "observed_at": payload["observed_at"],
            "content_hash": cls._content_hash(semantic_payload),
            "payload": payload,
        }

    @classmethod
    def _observation_row(
        cls, observation: IntelligenceObservation
    ) -> dict[str, Any]:
        payload = observation.model_dump(mode="json")
        semantic_payload = copy.deepcopy(payload)
        evidence_items = semantic_payload.get("evidence", [])
        if isinstance(evidence_items, list):
            for evidence in evidence_items:
                if isinstance(evidence, dict):
                    evidence.pop("collected_at", None)

        return {
            "source_id": observation.source_id,
            "observation_id": observation.observation_id,
            "entity_type": observation.entity_type,
            "entity_id": observation.entity_id,
            "observed_at": payload["observed_at"],
            "content_hash": cls._content_hash(semantic_payload),
            "payload": payload,
        }

    @staticmethod
    def _content_hash(payload: dict[str, Any]) -> str:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
