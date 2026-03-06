# -*- coding: utf-8 -*-
"""Tests for CapabilityAuthorizer - security authorization layer."""

import pytest

from app.application.security.capability_authorizer import CapabilityAuthorizer


class TestCapabilityAuthorizer:
    """Unit tests for CapabilityAuthorizer."""

    @pytest.fixture
    def authorizer(self):
        """Authorizer with a small, controlled allowlist for testing."""
        return CapabilityAuthorizer(
            allowlist={"allowed_cap", "sensitive_cap", "regular_cap"},
            require_confirmation_for={"sensitive_cap"},
        )

    # ------------------------------------------------------------------
    # Allowlist enforcement
    # ------------------------------------------------------------------

    def test_allowed_capability_passes(self, authorizer):
        """A whitelisted capability with valid payload should be authorized."""
        result = authorizer.authorize(user="alice", capability_name="regular_cap", payload={})
        assert result is True

    def test_capability_not_in_allowlist_raises_permission_error(self, authorizer):
        """Execution of a capability outside the allowlist must raise PermissionError."""
        with pytest.raises(PermissionError, match="não está na allowlist"):
            authorizer.authorize(user="alice", capability_name="unknown_cap", payload={})

    def test_empty_allowlist_blocks_all(self):
        """An authorizer with an empty allowlist blocks every capability."""
        authorizer = CapabilityAuthorizer(allowlist=set())
        with pytest.raises(PermissionError):
            authorizer.authorize(user="alice", capability_name="any_cap", payload={})

    # ------------------------------------------------------------------
    # Remote execution blocking
    # ------------------------------------------------------------------

    def test_remote_execution_without_authorization_is_blocked(self, authorizer):
        """remote=True without remote_authorized=True must be rejected."""
        with pytest.raises(PermissionError, match="Execução remota"):
            authorizer.authorize(
                user="alice",
                capability_name="regular_cap",
                payload={"remote": True},
            )

    def test_remote_execution_with_authorization_passes(self, authorizer):
        """remote=True with remote_authorized=True should be allowed."""
        result = authorizer.authorize(
            user="alice",
            capability_name="regular_cap",
            payload={"remote": True, "remote_authorized": True},
        )
        assert result is True

    # ------------------------------------------------------------------
    # Human confirmation for sensitive capabilities
    # ------------------------------------------------------------------

    def test_sensitive_capability_without_confirmation_is_blocked(self, authorizer):
        """Sensitive capability without human_confirmed=True must be rejected."""
        with pytest.raises(PermissionError, match="confirmação humana"):
            authorizer.authorize(
                user="alice",
                capability_name="sensitive_cap",
                payload={},
            )

    def test_sensitive_capability_with_confirmation_passes(self, authorizer):
        """Sensitive capability with human_confirmed=True should be authorized."""
        result = authorizer.authorize(
            user="alice",
            capability_name="sensitive_cap",
            payload={"human_confirmed": True},
        )
        assert result is True

    # ------------------------------------------------------------------
    # Payload injection detection
    # ------------------------------------------------------------------

    def test_payload_with_shell_semicolon_is_blocked(self, authorizer):
        """Payload containing ';' (shell metacharacter) must raise ValueError."""
        with pytest.raises(ValueError, match="padrão suspeito"):
            authorizer.authorize(
                user="alice",
                capability_name="regular_cap",
                payload={"command": "echo hello; rm -rf /"},
            )

    def test_payload_with_pipe_is_blocked(self, authorizer):
        """Payload containing '|' must raise ValueError."""
        with pytest.raises(ValueError, match="padrão suspeito"):
            authorizer.authorize(
                user="alice",
                capability_name="regular_cap",
                payload={"cmd": "ls | cat /etc/passwd"},
            )

    def test_payload_with_command_substitution_is_blocked(self, authorizer):
        """Payload containing '$()' must raise ValueError."""
        with pytest.raises(ValueError, match="padrão suspeito"):
            authorizer.authorize(
                user="alice",
                capability_name="regular_cap",
                payload={"text": "$(whoami)"},
            )

    def test_payload_with_path_traversal_is_blocked(self, authorizer):
        """Payload containing '../' (path traversal) must raise ValueError."""
        with pytest.raises(ValueError, match="padrão suspeito"):
            authorizer.authorize(
                user="alice",
                capability_name="regular_cap",
                payload={"path": "../../etc/passwd"},
            )

    def test_clean_payload_passes(self, authorizer):
        """A payload with safe string values should not be blocked."""
        result = authorizer.authorize(
            user="alice",
            capability_name="regular_cap",
            payload={"message": "Abrir o navegador", "url": "https://example.com"},
        )
        assert result is True

    def test_non_string_payload_values_are_ignored(self, authorizer):
        """Non-string payload values (int, bool, list) should not trigger injection check."""
        result = authorizer.authorize(
            user="alice",
            capability_name="regular_cap",
            payload={"count": 5, "active": True, "items": [1, 2, 3]},
        )
        assert result is True

    # ------------------------------------------------------------------
    # Dynamic allowlist management
    # ------------------------------------------------------------------

    def test_add_to_allowlist(self, authorizer):
        """Dynamically added capability should pass authorization."""
        authorizer.add_to_allowlist("new_cap")
        assert authorizer.is_allowed("new_cap") is True

    def test_remove_from_allowlist(self, authorizer):
        """Dynamically removed capability should fail authorization."""
        authorizer.remove_from_allowlist("regular_cap")
        assert authorizer.is_allowed("regular_cap") is False
        with pytest.raises(PermissionError):
            authorizer.authorize(user="alice", capability_name="regular_cap", payload={})

    def test_is_allowed_returns_false_for_unknown(self, authorizer):
        """is_allowed() returns False for capabilities not in the allowlist."""
        assert authorizer.is_allowed("nonexistent") is False


class TestCapabilityAuthorizerDefaultLists:
    """Tests verifying _DEFAULT_ALLOWLIST and _SENSITIVE_CAPABILITIES contents."""

    @pytest.fixture
    def default_authorizer(self):
        """Authorizer using the production default allowlist."""
        return CapabilityAuthorizer()

    # ------------------------------------------------------------------
    # New phase-2 auto-evolution components
    # ------------------------------------------------------------------

    def test_evolution_orchestrator_is_in_allowlist(self, default_authorizer):
        """evolution_orchestrator must be present in _DEFAULT_ALLOWLIST."""
        assert default_authorizer.is_allowed("evolution_orchestrator") is True

    def test_evolution_orchestrator_requires_human_confirmation(self, default_authorizer):
        """evolution_orchestrator is sensitive and must require human_confirmed."""
        with pytest.raises(PermissionError, match="confirmação humana"):
            default_authorizer.authorize(
                user="bot",
                capability_name="evolution_orchestrator",
                payload={},
            )

    def test_evolution_orchestrator_passes_with_confirmation(self, default_authorizer):
        """evolution_orchestrator with human_confirmed=True should be authorized."""
        result = default_authorizer.authorize(
            user="bot",
            capability_name="evolution_orchestrator",
            payload={"human_confirmed": True},
        )
        assert result is True

    def test_capability_index_service_is_allowed_without_confirmation(self, default_authorizer):
        """capability_index_service is not sensitive — no human confirmation required."""
        result = default_authorizer.authorize(
            user="bot",
            capability_name="capability_index_service",
            payload={},
        )
        assert result is True

    def test_cost_tracker_adapter_is_allowed(self, default_authorizer):
        """cost_tracker_adapter must be present in _DEFAULT_ALLOWLIST."""
        assert default_authorizer.is_allowed("cost_tracker_adapter") is True

    def test_procedural_memory_adapter_is_allowed(self, default_authorizer):
        """procedural_memory_adapter must be present in _DEFAULT_ALLOWLIST."""
        assert default_authorizer.is_allowed("procedural_memory_adapter") is True

    def test_overwatch_daemon_is_allowed(self, default_authorizer):
        """overwatch_daemon must be present in _DEFAULT_ALLOWLIST."""
        assert default_authorizer.is_allowed("overwatch_daemon") is True
