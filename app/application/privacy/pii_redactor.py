# -*- coding: utf-8 -*-
"""PII Redactor - sanitize Personally Identifiable Information before indexing.

No raw PII may be stored in the vector memory (FAISS).  All text must pass
through :class:`PiiRedactor` before embedding or indexing.

Supports:
- Email addresses
- Brazilian CPF numbers
- Phone numbers (Brazilian and international)
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII detection patterns
# ---------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# CPF: 000.000.000-00 or 00000000000 (11 digits)
_CPF_PATTERN = re.compile(
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
)

# Phone: Brazilian (+55 or 0) and generic international formats
_PHONE_PATTERN = re.compile(
    r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)(?:9\s?)?\d{4}[\s\-]?\d{4}\b"
    r"|\b(?:\+\d{1,3}[\s\-]?)?\(?\d{2,4}\)?[\s\-]?\d{3,5}[\s\-]?\d{4}\b",
)

_REDACTION_MAP = [
    (_EMAIL_PATTERN, "[EMAIL_REDACTED]"),
    (_CPF_PATTERN, "[CPF_REDACTED]"),
    (_PHONE_PATTERN, "[PHONE_REDACTED]"),
]


class PiiRedactor:
    """Sanitize text by replacing PII with safe placeholders.

    Designed to be used as a pre-processing step before any text is sent
    to an embedding model or stored in the vector index.

    Also maintains an internal purge registry so that events stored under a
    user identifier can be removed on request.

    Args:
        extra_patterns: Optional list of ``(pattern, placeholder)`` tuples to
            extend the default PII detection rules.
    """

    def __init__(
        self,
        extra_patterns: Optional[List[tuple]] = None,
    ) -> None:
        self._patterns = list(_REDACTION_MAP)
        if extra_patterns:
            self._patterns.extend(extra_patterns)
        # user_id -> list of event IDs registered for that user
        self._user_index: Dict[str, List[str]] = {}
        # event_id -> raw event record (text, metadata, …)
        self._events: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Core sanitisation
    # ------------------------------------------------------------------

    def sanitize(self, text: str) -> str:
        """Replace all detected PII in *text* with safe placeholders.

        Args:
            text: Raw input text that may contain PII.

        Returns:
            Sanitized version of *text* with PII replaced by placeholders.
        """
        if not text:
            return text
        result = text
        for pattern, placeholder in self._patterns:
            result = pattern.sub(placeholder, result)
        return result

    # ------------------------------------------------------------------
    # Event registry helpers (used by purge methods)
    # ------------------------------------------------------------------

    def register_event(
        self,
        user_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a (sanitized) event in the internal purge registry.

        Args:
            user_id: Owner of the event (used for ``purge_by_user``).
            text: Already-sanitized text to store.
            metadata: Optional metadata dict.

        Returns:
            The generated event ID (UUID string).
        """
        event_id = str(uuid.uuid4())
        self._events[event_id] = {
            "id": event_id,
            "user_id": user_id,
            "text": text,
            "metadata": metadata or {},
        }
        self._user_index.setdefault(user_id, []).append(event_id)
        return event_id

    # ------------------------------------------------------------------
    # Purge methods
    # ------------------------------------------------------------------

    def purge_by_user(self, user_id: str) -> int:
        """Remove all events registered for *user_id*.

        Args:
            user_id: The user whose data should be purged.

        Returns:
            Number of events removed.
        """
        event_ids = self._user_index.pop(user_id, [])
        for eid in event_ids:
            self._events.pop(eid, None)
        logger.info(
            "🗑️ [PiiRedactor] Purged %d event(s) for user '%s'.", len(event_ids), user_id
        )
        return len(event_ids)

    def purge_all(self) -> int:
        """Remove every event from the internal registry.

        Returns:
            Number of events removed.
        """
        count = len(self._events)
        self._events.clear()
        self._user_index.clear()
        logger.info("🗑️ [PiiRedactor] Purged all %d event(s).", count)
        return count
