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
        """Compare the router's existing task type against Laya's shadow prediction."""
        normalized_actual = actual_task_type if actual_task_type in _TASK_TYPES else "general"
        return self.submit_question(
            context, "task_type", _TASK_TYPE_QUESTION, normalized_actual,
            event_name="laya_shadow_decision",
        )

    def submit_question(
        self,
        context: Mapping[str, Any],
        question_name: str,
        question: Mapping[str, Any],
        expected_value: str,
        *,
        event_name: str = "laya_shadow_decision",
    ) -> bool:
        """Queue any typed choice comparison without changing application behavior."""
        if self._closed or not self._capacity.acquire(blocking=False):
            return False
        text = self._extract_text(context)
        if not text:
            self._capacity.release()
            return False
        try:
            future = self._executor.submit(
                self._evaluate_question, {"request": text[:8000]}, question_name,
                dict(question), str(expected_value), event_name,
            )
        except RuntimeError:
            self._capacity.release()
            return False
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

    def _evaluate_question(
        self,
        state: dict[str, str],
        question_name: str,
        question: dict[str, Any],
        expected_value: str,
        event_name: str,
    ) -> None:
        try:
            response = self.engine.decide(state, {question_name: question})
            answer = response["answers"][question_name]
            predicted = answer.get("choice")
            criteria = question.get("criteria")
            if not isinstance(criteria, Mapping) or predicted not in criteria:
                raise ValueError("Laya returned an unknown choice")
            confidence = answer.get("answer_confidence", answer.get("confidence"))
            event = {
                "event": event_name,
                "decision_type": question_name,
                "predicted_value": predicted,
                "existing_value": expected_value,
                "agreement": predicted == expected_value,
                "confidence": confidence if isinstance(confidence, (int, float)) else None,
                "model": (response.get("routing") or {}).get("model"),
            }
            if question_name == "task_type":
                event["predicted_task_type"] = predicted
                event["existing_task_type"] = expected_value
            logger.info("Laya shadow decision: %s", event)
            if self._event_sink is not None:
                self._event_sink(event)
        except Exception as exc:
            logger.debug("Laya shadow evaluation failed: %s", type(exc).__name__)

    def close(self, *, wait: bool = False) -> None:
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=True)
