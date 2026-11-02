"""Deterministic, evidence-preserving synthesis for public intelligence batches."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.domain.intelligence.contracts import (
    IntelligenceBatch,
    IntelligenceCorrelation,
    IntelligenceEvent,
    IntelligenceReport,
)


class IntelligenceCore:
    """Deduplicate exact source records and surface conservative correlation candidates.

    Correlations are hypotheses for review, never claims of independent corroboration.
    The service is pure: it performs no network calls, persistence, scheduling or delivery.
    """

    _CORRELATION_WINDOW = timedelta(hours=24)

    def process(self, batch: IntelligenceBatch | dict) -> IntelligenceReport:
        """Normalize a batch into unique events and explicit correlation candidates."""
        if not isinstance(batch, IntelligenceBatch):
            batch = IntelligenceBatch.model_validate(batch)

        unique: dict[tuple[str, str], IntelligenceEvent] = {}
        ordered = sorted(
            batch.events,
            key=lambda event: (
                event.source_id,
                event.event_id,
                str(event.url),
                self._as_utc(event.observed_at),
            ),
        )
        for event in ordered:
            unique.setdefault((event.source_id, event.event_id), event)

        events = tuple(
            sorted(
                unique.values(),
                key=lambda event: (
                    self._as_utc(event.occurred_at or event.published_at or event.observed_at),
                    event.source_id,
                    event.event_id,
                ),
            )
        )
        correlations = self._correlate(events)
        return IntelligenceReport(
            events=events,
            sources=batch.sources,
            correlations=correlations,
            input_event_count=len(batch.events),
            unique_event_count=len(events),
            duplicate_event_count=len(batch.events) - len(events),
        )

    @classmethod
    def _correlate(
        cls, events: tuple[IntelligenceEvent, ...]
    ) -> tuple[IntelligenceCorrelation, ...]:
        parents = list(range(len(events)))
        edge_bases: dict[tuple[int, int], set[str]] = {}

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parents[max(left_root, right_root)] = min(left_root, right_root)

        for left in range(len(events)):
            for right in range(left + 1, len(events)):
                basis = cls._correlation_basis(events[left], events[right])
                if basis is None:
                    continue
                edge_bases.setdefault((left, right), set()).add(basis)
                union(left, right)

        members: dict[int, list[int]] = {}
        for index in range(len(events)):
            root = find(index)
            members.setdefault(root, []).append(index)

        results: list[IntelligenceCorrelation] = []
        for indices in members.values():
            if len(indices) < 2:
                continue
            index_set = set(indices)
            bases = {
                basis
                for (left, right), values in edge_bases.items()
                if left in index_set and right in index_set
                for basis in values
            }
            basis = "same_url" if "same_url" in bases else "same_headline"
            event_ids = tuple(sorted(events[index].event_id for index in indices))
            identity = "|".join(event_ids)
            correlation_id = "corr:" + hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()[:24]
            results.append(
                IntelligenceCorrelation(
                    correlation_id=correlation_id,
                    event_ids=event_ids,
                    basis=basis,
                    status="candidate",
                    distinct_source_count=len(
                        {events[index].source_id for index in indices}
                    ),
                )
            )
        return tuple(sorted(results, key=lambda item: item.correlation_id))

    @classmethod
    def _correlation_basis(
        cls, left: IntelligenceEvent, right: IntelligenceEvent
    ) -> str | None:
        if cls._canonical_url(left.url) == cls._canonical_url(right.url):
            return "same_url"

        if (
            cls._title_fingerprint(left.title)
            and cls._title_fingerprint(left.title) == cls._title_fingerprint(right.title)
            and left.domain.casefold() == right.domain.casefold()
            and left.category.casefold() == right.category.casefold()
            and abs(cls._event_time(left) - cls._event_time(right))
            <= cls._CORRELATION_WINDOW
        ):
            return "same_headline"
        return None

    @staticmethod
    def _canonical_url(value: object) -> str:
        parsed = urlsplit(str(value))
        query = [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in {"fbclid", "gclid"}
        ]
        return urlunsplit(
            (
                parsed.scheme.casefold(),
                parsed.netloc.casefold(),
                parsed.path.rstrip("/") or "/",
                urlencode(sorted(query)),
                "",
            )
        )

    @staticmethod
    def _title_fingerprint(value: str) -> str:
        return re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).strip()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _event_time(cls, event: IntelligenceEvent) -> datetime:
        return cls._as_utc(
            event.occurred_at or event.published_at or event.observed_at
        )
