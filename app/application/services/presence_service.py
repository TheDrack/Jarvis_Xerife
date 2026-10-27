"""User-presence state machine for Jarvis phone/desktop sessions.

This service is deliberately hardware- and transport-independent. Callers feed
local activity and phone heartbeats; it never assumes that Tailscale connectivity
alone means a person is present.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Optional


class PresenceState(str, Enum):
    READY = "ready"
    ACTIVE = "active"
    AWAY = "away"
    SLEEP = "sleep"


@dataclass(frozen=True)
class PresenceSnapshot:
    state: PresenceState
    last_activity: datetime
    last_phone_heartbeat: Optional[datetime]
    reason: str


class PresenceService:
    """Thread-safe state machine driven by activity and phone heartbeat."""

    def __init__(self, idle_after: int = 300, sleep_after: int = 900,
                 heartbeat_timeout: int = 45) -> None:
        if idle_after < 1 or sleep_after <= idle_after or heartbeat_timeout < 1:
            raise ValueError("Require idle_after >= 1, sleep_after > idle_after, heartbeat_timeout >= 1")
        self.idle_after = timedelta(seconds=idle_after)
        self.sleep_after = timedelta(seconds=sleep_after)
        self.heartbeat_timeout = timedelta(seconds=heartbeat_timeout)
        now = datetime.now(timezone.utc)
        self._last_activity = now
        self._last_phone_heartbeat: Optional[datetime] = None
        self._state = PresenceState.READY
        self._reason = "startup"
        self._lock = RLock()

    @staticmethod
    def _utc(now: Optional[datetime]) -> datetime:
        value = now or datetime.now(timezone.utc)
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def activity(self, source: str = "desktop", now: Optional[datetime] = None) -> PresenceSnapshot:
        """Mark a real user interaction (keyboard/mouse/touch/voice)."""
        with self._lock:
            stamp = self._utc(now)
            self._last_activity = stamp
            self._state = PresenceState.ACTIVE
            self._reason = f"activity:{source}"
            if source == "phone":
                self._last_phone_heartbeat = stamp
            return self._snapshot_locked(stamp)

    def heartbeat(self, now: Optional[datetime] = None) -> PresenceSnapshot:
        """Record that the paired phone client is alive; does not assert user activity."""
        with self._lock:
            stamp = self._utc(now)
            self._last_phone_heartbeat = stamp
            return self._evaluate_locked(stamp)

    def evaluate(self, now: Optional[datetime] = None) -> PresenceSnapshot:
        with self._lock:
            return self._evaluate_locked(self._utc(now))

    def _evaluate_locked(self, stamp: datetime) -> PresenceSnapshot:
        elapsed = stamp - self._last_activity
        phone_alive = self._last_phone_heartbeat is not None and stamp - self._last_phone_heartbeat <= self.heartbeat_timeout
        if elapsed >= self.sleep_after and not phone_alive:
            self._state, self._reason = PresenceState.SLEEP, "idle_and_phone_disconnected"
        elif elapsed >= self.idle_after and not phone_alive:
            self._state, self._reason = PresenceState.AWAY, "idle_and_phone_disconnected"
        elif elapsed >= self.idle_after:
            self._state, self._reason = PresenceState.READY, "desktop_idle_phone_connected"
        else:
            self._state, self._reason = PresenceState.ACTIVE, "recent_activity"
        return self._snapshot_locked(stamp)

    def _snapshot_locked(self, now: datetime) -> PresenceSnapshot:
        return PresenceSnapshot(self._state, self._last_activity, self._last_phone_heartbeat, self._reason)
