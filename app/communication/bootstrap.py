"""Explicit construction of the default communication adapter set."""

from __future__ import annotations

from typing import Any

from app.communication.chatgpt_plan import ChatGPTPlanCommunicationAdapter
from app.communication.registry import CommunicationRegistry


def create_default_communication_registry(
    *, oauth_factory: Any = None, client_factory: Any = None
) -> CommunicationRegistry:
    """Build the default registry without probing providers or loading secrets."""
    kwargs = {}
    if oauth_factory is not None:
        kwargs["oauth_factory"] = oauth_factory
    if client_factory is not None:
        kwargs["client_factory"] = client_factory
    return CommunicationRegistry([ChatGPTPlanCommunicationAdapter(**kwargs)])
