"""Evidence-driven proactive initiative detection.

The engine only creates proposals. It never dispatches tools or executes actions.
Temporal patterns are inferred from repeated, timestamped observations rather than
from a single interaction or an LLM-generated guess.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class InitiativeCandidate:
    """A grounded opportunity that may be presented to the user."""

    key: str
    kind: str
    title: str
    message: str
    score: float
    confidence: float
    evidence: tuple[str, ...]
    suggested_at: str
    preparation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "title": self.title,
            "message": self.message,
            "score": self.score,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "suggested_at": self.suggested_at,
            "preparation": dict(self.preparation),
        }


class ProactiveInitiativeEngine:
    """Detect recurring moments and concrete help opportunities without side effects."""

    HELP_SIGNAL_KINDS = frozenset({
        "task_blocked",
        "deadline_approaching",
        "project_stalled",
        "repeated_failure",
        "dependency_missing",
    })
    _IGNORED_COMMANDS = {
        "oi", "ola", "olá", "bom dia", "boa tarde", "boa noite",
        "obrigado", "obrigada", "valeu", "ok", "sim", "nao", "não",
    }

    def __init__(
        self,
        *,
        timezone_name: str = "America/Sao_Paulo",
        quiet_hours: tuple[int, int] = (22, 7),
        min_recurrences: int = 3,
        history_days: int = 30,
        temporal_window_minutes: int = 35,
        cooldown_minutes: int = 12 * 60,
        minimum_score: float = 0.60,
    ) -> None:
        if timezone_name.upper() in {"UTC", "ETC/UTC", "GMT"}:
            self.timezone = timezone.utc
        else:
            try:
                self.timezone = ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError):
                # Windows Python may not ship an IANA database. Fall back to the
                # host's current local offset instead of silently assuming UTC.
                self.timezone = datetime.now().astimezone().tzinfo or timezone.utc
        if (
            len(quiet_hours) != 2
            or any(not isinstance(hour, int) or not 0 <= hour <= 23 for hour in quiet_hours)
        ):
            raise ValueError("quiet_hours must contain two hours between 0 and 23")
        if min_recurrences < 2 or history_days < 1 or temporal_window_minutes < 1:
            raise ValueError("recurrence and history limits must be positive")
        if cooldown_minutes < 0 or not 0 <= minimum_score <= 1:
            raise ValueError("invalid cooldown or minimum score")
        self.quiet_hours = quiet_hours
        self.min_recurrences = min_recurrences
        self.history_days = history_days
        self.temporal_window_minutes = temporal_window_minutes
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.minimum_score = minimum_score
        self._last_proposed: dict[str, datetime] = {}

    def evaluate(
        self,
        history: Iterable[Mapping[str, Any]] | None,
        *,
        signals: Iterable[Mapping[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> list[InitiativeCandidate]:
        """Return ranked, deduplicated proposals; never invokes a tool or model."""
        current = self._localize(now or datetime.now(self.timezone))
        if self._is_quiet(current):
            return []

        history_items = list(history or [])
        signal_items = list(signals or [])
        candidates = self._detect_temporal_patterns(history_items, current)
        candidates.extend(
            self._detect_help_opportunities(history_items, signal_items, current)
        )
        eligible = [
            candidate for candidate in candidates
            if candidate.score >= self.minimum_score and not self._in_cooldown(candidate.key, current)
        ]
        eligible.sort(key=lambda item: (-item.score, item.kind, item.key))
        return eligible

    def mark_proposed(self, candidate_key: str, *, now: datetime | None = None) -> None:
        """Start the cooldown only after a proposal was successfully delivered."""
        if not candidate_key:
            return
        self._last_proposed[candidate_key] = self._localize(now or datetime.now(self.timezone))

    def _detect_temporal_patterns(
        self, history: Iterable[Mapping[str, Any]], now: datetime
    ) -> list[InitiativeCandidate]:
        grouped: dict[str, list[tuple[datetime, Mapping[str, Any]]]] = defaultdict(list)
        cutoff = now - timedelta(days=self.history_days)
        for item in history:
            if not isinstance(item, Mapping) or item.get("success") is False:
                continue
            command = self._normalize_command(
                item.get("command") or item.get("user_input") or item.get("text")
            )
            timestamp = self._timestamp(item)
            if not command or command in self._IGNORED_COMMANDS or len(command) < 8:
                continue
            if timestamp is None or timestamp < cutoff or timestamp > now:
                continue
            grouped[command].append((timestamp, item))

        candidates: list[InitiativeCandidate] = []
        now_minute = now.hour * 60 + now.minute
        for command, records in grouped.items():
            distinct_days = {stamp.date() for stamp, _ in records}
            if len(distinct_days) < self.min_recurrences:
                continue
            minute_values = [stamp.hour * 60 + stamp.minute for stamp, _ in records]
            expected_minute = int(median(minute_values))
            distance = abs(now_minute - expected_minute)
            distance = min(distance, 1440 - distance)
            if distance > self.temporal_window_minutes:
                continue

            confidence = min(0.95, 0.70 + 0.05 * (len(distinct_days) - self.min_recurrences))
            urgency = max(0.55, 1.0 - distance / max(1, self.temporal_window_minutes) * 0.35)
            score = self._score(confidence, impact=0.58, urgency=urgency, availability=0.9, interruption=0.08)
            refs = tuple(
                str(item.get("event_id") or item.get("id") or stamp.isoformat())
                for stamp, item in sorted(records, key=lambda pair: pair[0])[-5:]
            )
            expected_time = f"{expected_minute // 60:02d}:{expected_minute % 60:02d}"
            title = f"Atividade recorrente: {command[:100]}"
            message = (
                f"Percebi que você costuma realizar '{command[:140]}' por volta de "
                f"{expected_time}. Quer que eu prepare o contexto para essa atividade?"
            )
            candidates.append(self._candidate(
                kind="temporal_pattern",
                title=title,
                message=message,
                score=score,
                confidence=confidence,
                evidence=refs,
                now=now,
                objective=f"Preparar contexto para a atividade recorrente: {command}",
                context={"observed_occurrences": len(distinct_days), "usual_local_time": expected_time},
            ))
        return candidates

    def _detect_help_opportunities(
        self,
        history: Iterable[Mapping[str, Any]],
        signals: Iterable[Mapping[str, Any]],
        now: datetime,
    ) -> list[InitiativeCandidate]:
        candidates: list[InitiativeCandidate] = []
        grouped_failures: dict[str, list[tuple[datetime, Mapping[str, Any]]]] = defaultdict(list)
        cutoff = now - timedelta(hours=24)

        for item in history:
            if not isinstance(item, Mapping) or item.get("success") is not False:
                continue
            command = self._normalize_command(
                item.get("command") or item.get("user_input") or item.get("text")
            )
            timestamp = self._timestamp(item)
            if command and timestamp and cutoff <= timestamp <= now:
                grouped_failures[command].append((timestamp, item))

        for command, failures in grouped_failures.items():
            if len(failures) < 2:
                continue
            refs = tuple(
                str(item.get("event_id") or item.get("id") or stamp.isoformat())
                for stamp, item in sorted(failures, key=lambda pair: pair[0])[-5:]
            )
            confidence = min(0.95, 0.78 + 0.04 * (len(failures) - 2))
            score = self._score(confidence, impact=0.72, urgency=0.72, availability=0.9, interruption=0.08)
            candidates.append(self._candidate(
                kind="help_opportunity",
                title=f"Falha recorrente: {command[:100]}",
                message=(
                    f"Notei que '{command[:120]}' falhou {len(failures)} vezes nas últimas 24 horas. "
                    "Posso investigar a causa e preparar uma correção."
                ),
                score=score,
                confidence=confidence,
                evidence=refs,
                now=now,
                objective=f"Investigar as falhas recorrentes da atividade: {command}",
                context={"failure_count_24h": len(failures)},
            ))

        for signal in signals:
            if not isinstance(signal, Mapping):
                continue
            kind = str(signal.get("kind") or "").strip().lower()
            if kind not in self.HELP_SIGNAL_KINDS:
                continue
            signal_time = self._timestamp(signal)
            if signal_time is not None and not now - timedelta(hours=24) <= signal_time <= now:
                continue
            title = self._clean(signal.get("title") or signal.get("name") or kind, 180)
            if not title:
                continue
            confidence = self._unit(signal.get("confidence"), 0.75)
            impact = self._unit(signal.get("impact"), 0.70)
            urgency = self._unit(signal.get("urgency"), 0.70)
            availability = self._unit(signal.get("availability"), 0.90)
            interruption = self._unit(signal.get("interruption_cost"), 0.10)
            score = self._score(confidence, impact, urgency, availability, interruption)
            evidence_ref = self._clean(signal.get("evidence_ref") or signal.get("event_id"), 200)
            evidence = (evidence_ref,) if evidence_ref else ()
            objective = self._clean(
                signal.get("objective") or f"Investigar e preparar ajuda para: {title}", 500
            )
            candidates.append(self._candidate(
                kind="help_opportunity",
                title=f"Oportunidade de ajuda: {title}",
                message=(
                    f"Identifiquei um ponto que pode precisar de ajuda: {title}. "
                    "Posso investigar e preparar os próximos passos."
                ),
                score=score,
                confidence=confidence,
                evidence=evidence,
                now=now,
                objective=objective,
                context={"signal_kind": kind},
            ))
        return candidates

    def _candidate(
        self,
        *,
        kind: str,
        title: str,
        message: str,
        score: float,
        confidence: float,
        evidence: tuple[str, ...],
        now: datetime,
        objective: str,
        context: dict[str, Any],
    ) -> InitiativeCandidate:
        fingerprint = f"{kind}:{self._normalize_command(title)}"
        key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
        return InitiativeCandidate(
            key=key,
            kind=kind,
            title=title,
            message=message,
            score=round(max(0.0, min(1.0, score)), 4),
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            evidence=evidence,
            suggested_at=now.isoformat(),
            preparation={
                "objective": objective,
                "context": context,
                "evidence": list(evidence),
                "execution_mode": "proposal_only",
                "requires_user_approval": True,
            },
        )

    def _in_cooldown(self, key: str, now: datetime) -> bool:
        last = self._last_proposed.get(key)
        if last is None:
            return False
        if now - last < self.cooldown:
            return True
        self._last_proposed.pop(key, None)
        return False

    def _is_quiet(self, now: datetime) -> bool:
        start, end = self.quiet_hours
        if start == end:
            return False
        if start < end:
            return start <= now.hour < end
        return now.hour >= start or now.hour < end

    def _timestamp(self, item: Mapping[str, Any]) -> datetime | None:
        value = item.get("timestamp") or item.get("_ts") or item.get("created_at") or item.get("observed_at")
        if isinstance(value, datetime):
            return self._localize(value)
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return self._localize(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
        except ValueError:
            return None

    def _localize(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=self.timezone)
        return value.astimezone(self.timezone)

    @staticmethod
    def _normalize_command(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        normalized = unicodedata.normalize("NFKC", value).casefold()
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        return " ".join(normalized.split())[:300]

    @staticmethod
    def _clean(value: Any, limit: int) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.split())[:limit]

    @staticmethod
    def _unit(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if parsed != parsed:
            return default
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _score(
        confidence: float,
        impact: float,
        urgency: float,
        availability: float,
        interruption: float,
    ) -> float:
        return (
            0.40 * confidence
            + 0.25 * impact
            + 0.20 * urgency
            + 0.15 * availability
            - 0.10 * interruption
        )
