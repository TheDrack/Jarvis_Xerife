"""Persistence layer around the stateless remote model call.

The Termux worker's reasoning runs on the remote API, but completing an
objective is a stateful job: an attempt can end because the phone slept, the
network dropped or the lease expired. This handler records each attempt's
progress in the local journal before and after the model call, feeds recorded
progress back into the next attempt, and replays a stored successful result
when the queue retries a task whose completion never reached the server.

Enable it on the device with ``JARVIS_OBJECTIVE_JOURNAL_ENABLED=true``; it is
off by default so other runtimes keep their current behaviour.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

from .objective_journal import (
    AttemptContext,
    ObjectiveJournal,
    default_journal_path,
)
from .transport import AgentMessage

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 16000
INCOMPLETE_ERROR_TYPE = "objective_incomplete"
_TRUTHY = {"1", "true", "yes", "on"}
Handler = Callable[[AgentMessage], Mapping[str, Any]]


def objective_journal_enabled() -> bool:
    return os.getenv("JARVIS_OBJECTIVE_JOURNAL_ENABLED", "false").strip().lower() in _TRUTHY


class PersistentObjectiveHandler:
    """Wrap a remote inference handler so objective progress is durable."""

    def __init__(
        self,
        handler: Handler,
        journal: ObjectiveJournal,
    ) -> None:
        if not callable(handler):
            raise TypeError("handler must be callable")
        self.handler = handler
        self.journal = journal

    def __call__(self, message: AgentMessage) -> Mapping[str, Any]:
        if message.kind != "request":
            return self.handler(message)
        payload = message.payload
        attempt_id = str(payload.get("attempt_id") or "").strip()
        objective = payload.get("objective")
        if not attempt_id or not isinstance(objective, str) or not objective.strip():
            return self.handler(message)

        try:
            context = self.journal.begin_attempt(
                task_id=message.task_id,
                agent_id=message.recipient_id or "unknown-agent",
                objective=objective,
                attempt_id=attempt_id,
                acceptance_criteria=_criteria(payload.get("acceptance_criteria")),
            )
        except Exception as exc:  # noqa: BLE001 - persistence must not stop inference
            logger.warning(
                "Objective journal unavailable; continuing without local persistence "
                "(error_type=%s)",
                type(exc).__name__,
            )
            return self.handler(message)

        if context.completed_result is not None:
            logger.info(
                "Objective already completed in a persisted attempt; replaying the "
                "stored result (task_id=%s)",
                message.task_id,
            )
            return {**context.completed_result, "replayed_from_journal": True}

        enriched = self._with_continuation(message, context)
        step_index = self._start_step(message.task_id, attempt_id)
        try:
            result = self.handler(enriched)
        except Exception as exc:  # noqa: BLE001 - record, then propagate unchanged
            self._finish_step(
                message.task_id, attempt_id, step_index, status="interrupted"
            )
            self._note_failure(message.task_id, type(exc).__name__)
            raise

        mapping = dict(result) if isinstance(result, Mapping) else {}
        succeeded = mapping.get("success") is True
        self._finish_step(
            message.task_id,
            attempt_id,
            step_index,
            # Only model output is kept: error text can echo provider data.
            output=str(mapping.get("output") or "") if succeeded else "",
            status="completed" if succeeded else "failed",
        )
        if succeeded:
            try:
                self.journal.complete(task_id=message.task_id, result=mapping)
            except Exception as exc:  # noqa: BLE001 - the result still goes to the API
                logger.warning(
                    "Objective journal could not store the completed objective "
                    "(task_id=%s, error_type=%s)",
                    message.task_id,
                    type(exc).__name__,
                )
        else:
            self._note_failure(message.task_id, INCOMPLETE_ERROR_TYPE)
        return result

    def _with_continuation(
        self, message: AgentMessage, context: AttemptContext
    ) -> AgentMessage:
        """Append the journal digest to the context the model already receives."""
        if not context.is_resumed:
            return message
        try:
            digest = self.journal.continuation_context(message.task_id)
        except Exception as exc:  # noqa: BLE001 - degrade to unjournaled inference
            logger.warning(
                "Could not read journal progress; continuing without prior context "
                "(error_type=%s)",
                type(exc).__name__,
            )
            return message
        if not digest:
            return message
        payload = dict(message.payload)
        existing = payload.get("context")
        prior = existing if isinstance(existing, str) else ""
        # Reserve room for the digest so a long remote context cannot truncate it.
        prior = prior[: max(0, MAX_CONTEXT_CHARS - len(digest) - 2)]
        combined = "\n\n".join(part for part in (prior, digest) if part.strip())
        payload["context"] = combined[:MAX_CONTEXT_CHARS]
        return AgentMessage.create(
            task_id=message.task_id,
            sender_id=message.sender_id,
            recipient_id=message.recipient_id,
            kind=message.kind,
            payload=payload,
            correlation_id=message.correlation_id,
        )

    def _start_step(self, task_id: str, attempt_id: str) -> int | None:
        try:
            return self.journal.start_step(task_id=task_id, attempt_id=attempt_id)
        except Exception as exc:  # noqa: BLE001 - keep inference running
            logger.warning(
                "Objective journal could not record the step start (error_type=%s)",
                type(exc).__name__,
            )
            return None

    def _finish_step(
        self,
        task_id: str,
        attempt_id: str,
        step_index: int | None,
        *,
        output: str = "",
        status: str,
    ) -> None:
        if step_index is None:
            return
        try:
            self.journal.finish_step(
                task_id=task_id,
                attempt_id=attempt_id,
                step_index=step_index,
                output=output,
                status=status,
            )
        except Exception as exc:  # noqa: BLE001 - keep inference running
            logger.warning(
                "Objective journal could not record the step outcome (error_type=%s)",
                type(exc).__name__,
            )

    def _note_failure(self, task_id: str, error_type: str) -> None:
        try:
            self.journal.note_failure(task_id=task_id, error_type=error_type)
        except Exception as exc:  # noqa: BLE001 - keep inference running
            logger.warning(
                "Objective journal could not record the failure class (error_type=%s)",
                type(exc).__name__,
            )


def _criteria(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def wrap_handler_with_objective_journal(handler: Handler) -> Handler:
    """Return the journal-backed handler, or the original one when disabled.

    A journal that cannot be opened must not prevent the queue worker from
    starting: the phone still consumes tasks, just without local persistence.
    """
    if not objective_journal_enabled():
        return handler
    path = default_journal_path()
    try:
        journal = ObjectiveJournal(path)
    except Exception as exc:  # noqa: BLE001 - fail open to unjournaled inference
        logger.warning(
            "Objective journal is enabled but unavailable at %s; continuing without "
            "local persistence (error_type=%s)",
            path,
            type(exc).__name__,
        )
        return handler
    logger.info("Objective journal enabled at %s", path)
    return PersistentObjectiveHandler(handler, journal)


__all__ = [
    "PersistentObjectiveHandler",
    "objective_journal_enabled",
    "wrap_handler_with_objective_journal",
]
