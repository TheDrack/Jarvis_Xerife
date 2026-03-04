# -*- coding: utf-8 -*-
"""Capability Authorizer - Security layer for capability execution.

No capability may be executed without passing through explicit authorization.
Implements allowlist checking, remote execution blocking, human confirmation
requirements for sensitive commands, and payload injection detection.
"""

import logging
import re
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# Patterns that indicate shell injection or command execution attempts
_INJECTION_PATTERNS: list = [
    re.compile(r"[;&|`$]"),                   # shell metacharacters
    re.compile(r"\.\./"),                      # path traversal
    re.compile(r"<\s*\("),                     # process substitution
    re.compile(r"\$\(.*\)"),                   # command substitution
    re.compile(r"\b(eval|exec|system|popen|subprocess|os\.system)\b", re.IGNORECASE),
    re.compile(r"\b(rm\s+-rf|chmod|chown|sudo|su\s+)\b", re.IGNORECASE),
]

# Capabilities that require explicit human confirmation before execution
_SENSITIVE_CAPABILITIES: Set[str] = {
    "system_executor",
    "auto_evolution",
    "github_worker",
    "pyinstaller_builder",
    "drive_uploader",
    "gist_uploader",
    "delete_file",
    "format_disk",
}

# Default allowlist of approved capabilities
_DEFAULT_ALLOWLIST: Set[str] = {
    "assistant_service",
    "command_interpreter",
    "intent_processor",
    "memory_manager",
    "vector_memory_adapter",
    "notification_service",
    "telegram_adapter",
    "gemini_adapter",
    "gateway_llm_adapter",
    "sqlite_history_adapter",
    "vision_adapter",
    "field_vision",
    "thought_log_service",
    "strategist_service",
    "task_runner",
    "browser_manager",
    "github_worker",
    "system_executor",
    "auto_evolution",
    "audit_logger",
}


class CapabilityAuthorizer:
    """Authorization layer that guards capability execution.

    Args:
        allowlist: Set of capability names permitted to execute.
            Defaults to the project-wide ``_DEFAULT_ALLOWLIST``.
        require_confirmation_for: Set of capability names that need explicit
            human confirmation via the *context* payload.
    """

    def __init__(
        self,
        allowlist: Optional[Set[str]] = None,
        require_confirmation_for: Optional[Set[str]] = None,
    ) -> None:
        self._allowlist: Set[str] = allowlist if allowlist is not None else set(_DEFAULT_ALLOWLIST)
        self._sensitive: Set[str] = (
            require_confirmation_for
            if require_confirmation_for is not None
            else set(_SENSITIVE_CAPABILITIES)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def authorize(
        self,
        user: str,
        capability_name: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluate whether *user* may execute *capability_name* with *payload*.

        Args:
            user: Identifier of the requesting user/session.
            capability_name: Name of the capability to authorize.
            payload: Execution context / parameters. May be ``None``.

        Returns:
            ``True`` when the execution is authorized.

        Raises:
            PermissionError: When the capability is not in the allowlist or
                execution is blocked for another security reason.
            ValueError: When the payload contains suspicious patterns.
        """
        payload = payload or {}

        # 1. Allowlist check
        if capability_name not in self._allowlist:
            logger.warning(
                "🚫 [Authorizer] Capability '%s' não está na allowlist. Usuário: %s",
                capability_name,
                user,
            )
            raise PermissionError(
                f"Capability '{capability_name}' não autorizada: não está na allowlist."
            )

        # 2. Block unauthorized remote execution
        if payload.get("remote", False) and not payload.get("remote_authorized", False):
            logger.warning(
                "🚫 [Authorizer] Execução remota não autorizada de '%s'. Usuário: %s",
                capability_name,
                user,
            )
            raise PermissionError(
                f"Execução remota de '{capability_name}' bloqueada: autorização remota ausente."
            )

        # 3. Sensitive capabilities require human confirmation
        if capability_name in self._sensitive and not payload.get("human_confirmed", False):
            logger.warning(
                "🚫 [Authorizer] Capability sensível '%s' requer confirmação humana. Usuário: %s",
                capability_name,
                user,
            )
            raise PermissionError(
                f"Capability '{capability_name}' requer confirmação humana explícita "
                f"(payload 'human_confirmed': true)."
            )

        # 4. Payload injection scan
        self._check_payload_for_injection(capability_name, payload)

        logger.info(
            "✅ [Authorizer] '%s' autorizada para usuário '%s'.", capability_name, user
        )
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_payload_for_injection(
        self, capability_name: str, payload: Dict[str, Any]
    ) -> None:
        """Scan all string values in *payload* for injection patterns.

        Raises:
            ValueError: When a suspicious pattern is detected.
        """
        for key, value in payload.items():
            if not isinstance(value, str):
                continue
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(value):
                    logger.error(
                        "💉 [Authorizer] Payload suspeito detectado em '%s.%s': padrão '%s'.",
                        capability_name,
                        key,
                        pattern.pattern,
                    )
                    raise ValueError(
                        f"Payload bloqueado: campo '{key}' contém padrão suspeito de injeção."
                    )

    def add_to_allowlist(self, capability_name: str) -> None:
        """Dynamically add a capability to the allowlist."""
        self._allowlist.add(capability_name)

    def remove_from_allowlist(self, capability_name: str) -> None:
        """Dynamically remove a capability from the allowlist."""
        self._allowlist.discard(capability_name)

    def is_allowed(self, capability_name: str) -> bool:
        """Return ``True`` if *capability_name* is in the allowlist."""
        return capability_name in self._allowlist
