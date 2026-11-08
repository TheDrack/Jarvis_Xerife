"""Bounded, non-blocking shadow evaluation against a local Laya service."""
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)
_TASK_TYPES = {
    "code_repair": "Repair an existing software defect or regression",
    "code_generation": "Create or implement software code",
    "planning": "Plan work, architecture, or a sequence of actions",
    "evolution": "Analyze and improve Jarvis or its own capabilities",
    "vision": "Interpret an image, screen, camera, or visual input",
    "general": "General conversation, information, or an unclassified task",
}
_TASK_TYPE_QUESTION = {
    "type": "choice",
    "instructions": "Which task category best describes the user's request?",
    "criteria": _TASK_TYPES,
}

class LayaDecisionShadowObserver:
    """Compares Laya predictions with existing routing without influencing it."""
    def __init__(self, engine: Any, *, max_workers: int = 1, max_pending: int = 8,
                 event_sink: Callable[[dict[str, Any]], None] | None = None) -> None:
        if max_workers < 1 or max_pending < 1:
            raise ValueError("max_workers and max_pending must be positive")
        self.engine = engine
        self._executor = ThreadPoolExecutor(max_workers=max_workers,
                                            thread_name_prefix="jarvis-laya-shadow")
        self._capacity = BoundedSemaphore(max_pending)
        self._event_sink = event_sink
        self._closed = False

    def submit(self, context: Mapping[str, Any], actual_task_type: str) -> bool:
        """Queue a shadow sample; return immediately and never alter routing."""
        if self._closed or not self._capacity.acquire(blocking=False):
            return False
        text = self._extract_text(context)
        if not text:
            self._capacity.release()
            return False
        future = self._executor.submit(self._evaluate, {"request": text[:8000]}, actual_task_type)
        future.add_done_callback(lambda _future: self._capacity.release())
        return True

    @staticmethod
    def _extract_text(context: Mapping[str, Any]) -> str:
        for value in (context.get("prompt"), context.get("objective"),
                      context.get("text"), context.get("message")):
            if isinstance(value, str) and value.strip():
                return value.strip()
        messages = context.get("messages")
        if isinstance(messages, list):
            parts = [item.get("content", "") for item in messages
                     if isinstance(item, dict) and item.get("role") == "user"
                     and isinstance(item.get("content"), str)]
            return "\n".join(parts).strip()
        return ""

    def _evaluate(self, state: dict[str, str], actual_task_type: str) -> None:
        try:
            response = self.engine.decide(state, {"task_type": _TASK_TYPE_QUESTION})
            answer = response["answers"]["task_type"]
            predicted = answer.get("choice")
            if predicted not in _TASK_TYPES:
                raise ValueError("Laya returned an unknown task category")
            confidence = answer.get("answer_confidence", answer.get("confidence"))
            normalized_actual = actual_task_type if actual_task_type in _TASK_TYPES else "general"
            event = {
                "event": "laya_shadow_decision",
                "predicted_task_type": predicted,
                "existing_task_type": normalized_actual,
                "agreement": predicted == normalized_actual,
                "confidence": confidence if isinstance(confidence, (int, float)) else None,
                "model": (response.get("routing") or {}).get("model"),
            }
            logger.info("Laya shadow decision: %s", event)
            if self._event_sink is not None:
                self._event_sink(event)
        except Exception as exc:
            logger.debug("Laya shadow evaluation failed: %s", type(exc).__name__)

    def close(self, *, wait: bool = False) -> None:
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=True)
