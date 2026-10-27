from datetime import datetime, timezone, timedelta

from app.application.services.presence_service import PresenceService, PresenceState


def test_activity_sets_active_and_phone_source_updates_heartbeat():
    svc = PresenceService(idle_after=10, sleep_after=20, heartbeat_timeout=5)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snap = svc.activity("phone", now)
    assert snap.state is PresenceState.ACTIVE
    assert snap.last_phone_heartbeat == now


def test_idle_transitions_to_away_then_sleep_without_phone():
    svc = PresenceService(idle_after=10, sleep_after=20, heartbeat_timeout=5)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    svc.activity("desktop", now)
    assert svc.evaluate(now + timedelta(seconds=10)).state is PresenceState.AWAY
    assert svc.evaluate(now + timedelta(seconds=20)).state is PresenceState.SLEEP


def test_phone_heartbeat_prevents_sleep_but_does_not_fake_activity():
    svc = PresenceService(idle_after=10, sleep_after=20, heartbeat_timeout=30)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    svc.activity("desktop", now)
    assert svc.heartbeat(now + timedelta(seconds=15)).state is PresenceState.READY
    assert svc.evaluate(now + timedelta(seconds=25)).state is PresenceState.READY


def test_invalid_thresholds_rejected():
    try:
        PresenceService(idle_after=20, sleep_after=10)
        assert False, "expected ValueError"
    except ValueError:
        pass
