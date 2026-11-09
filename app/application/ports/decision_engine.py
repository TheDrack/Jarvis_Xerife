"""Provider-neutral contract for discriminative decision engines."""
from __future__ import annotations
from typing import Any, Mapping, Protocol, runtime_checkable

@runtime_checkable
class DecisionEngine(Protocol):
    """A typed, non-generative decision provider."""
    def decide(self, state: Mapping[str, Any], questions: Mapping[str, Any]) -> dict[str, Any]:
        """Return normalized typed answers and provider metadata."""
