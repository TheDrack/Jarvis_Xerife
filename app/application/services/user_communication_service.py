"""Policy and delivery orchestration for proactive Jarvis-to-user communication.

This layer makes deterministic decisions; it does not invent context or call an
LLM. Context producers must provide a grounded event, priority, and presence.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CommunicationPriority(IntEnum):
    INFO = 10
    NORMAL = 20
    URGENT = 30
    CRITICAL = 40


@dataclass(frozen=True)
class CommunicationDecision:
    status: str
    channel: str | None = None
    reason: str = ""


class UserCommunicationService:
    """Presence-aware communication policy with in-process dedupe and throttling.

    The caller supplies a transport callback. Deduplication and rate limits are
    intentionally process-local; durable dedupe requires a database schema.
    """

    def __init__(self, *, dedupe_seconds: int = 300, max_per_minute: int = 4,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if dedupe_seconds < 1 or max_per_minute < 1:
            raise ValueError("dedupe_seconds and max_per_minute must be positive")
        self._dedupe_seconds = dedupe_seconds
        self._max_per_minute = max_per_minute
        self._clock = clock
        self._sent: dict[str, float] = {}
        self._recent: deque[float] = deque()
        self._lock = threading.RLock()

    def decide(self, *, event_key: str, message: str, priority: CommunicationPriority,
               presence: str) -> CommunicationDecision:
        key = str(event_key or "").strip()
        text = str(message or "").strip()
        state = str(presence or "unknown").strip().lower()
        if not key or not text:
            return CommunicationDecision("rejected", reason="missing_event_key_or_message")
        if len(text) > 1000:
            return CommunicationDecision("rejected", reason="message_too_long")
        if state == "sleep" and priority < CommunicationPriority.URGENT:
            return CommunicationDecision("deferred", reason="user_sleeping_nonurgent")
        if state == "unknown" and priority < CommunicationPriority.URGENT:
            return CommunicationDecision("deferred", reason="presence_unknown_nonurgent")
        # Speak only when urgency warrants interruption; ordinary updates are visual.
        channel = "speak" if priority >= CommunicationPriority.URGENT else "notification"
        return CommunicationDecision("ready", channel=channel, reason="policy_allowed")

    def communicate(self, *, event_key: str, message: str,
                    priority: CommunicationPriority = CommunicationPriority.NORMAL,
                    presence: str = "unknown",
                    dispatch: Callable[[str, str], Any]) -> dict[str, Any]:
        decision = self.decide(event_key=event_key, message=message,
                               priority=priority, presence=presence)
        if decision.status != "ready":
            return {"status": decision.status, "reason": decision.reason}
        now = self._clock()
        key = str(event_key).strip()
        with self._lock:
            self._sent = {k: stamp for k, stamp in self._sent.items()
                          if now - stamp < self._dedupe_seconds}
            while self._recent and now - self._recent[0] >= 60:
                self._recent.popleft()
            if key in self._sent:
                return {"status": "deduplicated", "reason": "event_recently_sent"}
            if priority < CommunicationPriority.URGENT and len(self._recent) >= self._max_per_minute:
                return {"status": "rate_limited", "reason": "nonurgent_rate_limit"}
            try:
                result = dispatch(decision.channel or "notification", message.strip())
            except Exception as exc:
                logger.warning("User communication delivery failed (%s)", type(exc).__name__)
                return {"status": "failed", "reason": "transport_error"}
            if isinstance(result, dict) and result.get("success") is False:
                return {"status": "failed", "reason": "transport_not_confirmed"}
            self._sent[key] = now
            if priority < CommunicationPriority.URGENT:
                self._recent.append(now)
            return {"status": "sent", "channel": decision.channel, "result": result}


def dispatch_to_mobile(channel: str, message: str) -> dict[str, Any]:
    """Deliver via existing native WebSocket; queue through Supabase if offline."""
    user_id = os.getenv("JARVIS_MOBILE_USER_ID", "").strip()
    device_id = os.getenv("JARVIS_MOBILE_DEVICE_ID", "").strip()
    if not user_id or not device_id:
        raise RuntimeError("Mobile communication target is not configured")
    from app.core.nexus import nexus
    manager = nexus.resolve("soldier_bridge")
    canonical_id = f"mobile:{user_id}:{device_id}"
    if manager is not None and manager.is_device_connected(canonical_id):
        import asyncio
        task = {"action": channel, "parameters": {"title": "Jarvis", "text": message}}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(manager.send_task(canonical_id, task, api_key=None))
        else:
            # The synchronous service may be called from an async host.
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(asyncio.run, manager.send_task(canonical_id, task, api_key=None)).result()
        if not isinstance(result, dict) or not result.get("success", False):
            raise RuntimeError("Mobile WebSocket delivery was not confirmed")
        return {"transport": "websocket", "device_id": device_id}
    from app.adapters.infrastructure.routers.mobile_push import queue_mobile_event
    queued = queue_mobile_event(user_id, device_id, message, mode=channel, title="Jarvis")
    return {"transport": "queue", **queued}
