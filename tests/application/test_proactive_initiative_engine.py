from datetime import datetime, timezone

from app.application.services.proactive_initiative_engine import ProactiveInitiativeEngine


TZ = timezone.utc


def _history(days, *, command="revisar o relatório diário", hour=9, minute=0):
    return [
        {
            "command": command,
            "success": True,
            "timestamp": datetime(2026, 11, day, hour, minute, tzinfo=TZ).isoformat(),
        }
        for day in days
    ]


def test_detects_repeated_activity_near_its_observed_time():
    engine = ProactiveInitiativeEngine(timezone_name="UTC")
    now = datetime(2026, 11, 7, 8, 45, tzinfo=TZ)

    candidates = engine.evaluate(_history([2, 4, 6]), now=now)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind == "temporal_pattern"
    assert "relatório diário" in candidate.message
    assert candidate.preparation["execution_mode"] == "proposal_only"
    assert candidate.preparation["requires_user_approval"] is True
    assert len(candidate.evidence) == 3


def test_does_not_infer_a_routine_from_too_few_observations():
    engine = ProactiveInitiativeEngine(timezone_name="UTC")
    now = datetime(2026, 11, 7, 8, 45, tzinfo=TZ)

    assert engine.evaluate(_history([5, 6]), now=now) == []


def test_detects_a_concrete_help_opportunity_from_a_blocked_signal():
    engine = ProactiveInitiativeEngine(timezone_name="UTC")
    now = datetime(2026, 11, 7, 10, 0, tzinfo=TZ)

    candidates = engine.evaluate(
        [],
        signals=[{
            "kind": "task_blocked",
            "title": "Integração do módulo de memória",
            "evidence_ref": "task:mem-42",
            "confidence": 0.9,
            "impact": 0.8,
            "urgency": 0.8,
        }],
        now=now,
    )

    assert len(candidates) == 1
    assert candidates[0].kind == "help_opportunity"
    assert candidates[0].evidence == ("task:mem-42",)
    assert candidates[0].preparation["objective"].startswith("Investigar")


def test_quiet_hours_suppress_proactive_notifications():
    engine = ProactiveInitiativeEngine(
        timezone_name="UTC",
        quiet_hours=(22, 7),
    )
    now = datetime(2026, 11, 7, 6, 30, tzinfo=TZ)

    candidates = engine.evaluate(
        [],
        signals=[{"kind": "task_blocked", "title": "Tarefa bloqueada"}],
        now=now,
    )

    assert candidates == []


def test_proposed_candidate_is_suppressed_during_cooldown():
    engine = ProactiveInitiativeEngine(timezone_name="UTC", cooldown_minutes=60)
    now = datetime(2026, 11, 7, 10, 0, tzinfo=TZ)
    signals = [{"kind": "task_blocked", "title": "Tarefa bloqueada", "evidence_ref": "task:1"}]

    candidate = engine.evaluate([], signals=signals, now=now)[0]
    engine.mark_proposed(candidate.key, now=now)

    assert engine.evaluate([], signals=signals, now=now.replace(minute=30)) == []


def test_invalid_history_records_are_ignored():
    engine = ProactiveInitiativeEngine(timezone_name="UTC")
    now = datetime(2026, 11, 7, 9, 0, tzinfo=TZ)

    candidates = engine.evaluate(
        [{"command": "revisar relatório", "timestamp": "not-a-date"}],
        now=now,
    )

    assert candidates == []
