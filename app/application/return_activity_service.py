"""Detect a genuine return to activity after an idle period."""

from dataclasses import dataclass


@dataclass
class ReturnActivityDetector:
    """Emit one event when input resumes after ``idle_threshold_seconds``.

    The detector is deliberately clock/API agnostic so its transition logic can
    be tested without a Windows desktop session.
    """

    idle_threshold_seconds: float = 300.0
    _was_idle: bool = False

    def __post_init__(self) -> None:
        if self.idle_threshold_seconds <= 0:
            raise ValueError("idle_threshold_seconds must be positive")

    @property
    def was_idle(self) -> bool:
        return self._was_idle

    def observe(self, idle_seconds: float) -> bool:
        """Return True exactly once when activity resumes after a long idle."""
        if idle_seconds < 0:
            raise ValueError("idle_seconds cannot be negative")
        if idle_seconds >= self.idle_threshold_seconds:
            self._was_idle = True
            return False
        if self._was_idle:
            self._was_idle = False
            return True
        return False
