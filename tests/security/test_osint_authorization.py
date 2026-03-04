# -*- coding: utf-8 -*-
"""Tests for OSINT capability authorization.

Validates that OSINT searches fail when the CapabilityAuthorizer blocks the
request, and succeed only when the capability is properly authorized with
explicit human confirmation.
"""

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.application.security.capability_authorizer import (
    CapabilityAuthorizer,
    _DEFAULT_ALLOWLIST,
    _SENSITIVE_CAPABILITIES,
)
from app.adapters.infrastructure.osint.eagle_osint_adapter import EagleOsintAdapter
from app.application.privacy.pii_redactor import PiiRedactor
from app.utils import jrvs_codec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def authorizer_with_osint():
    """Authorizer that includes osint_search in its allowlist and sensitive set."""
    return CapabilityAuthorizer(
        allowlist={"osint_search", "eagle_osint_adapter"},
        require_confirmation_for={"osint_search"},
    )


@pytest.fixture
def permissive_authorizer():
    """Authorizer that authorizes osint_search without requiring confirmation."""
    return CapabilityAuthorizer(
        allowlist={"osint_search", "eagle_osint_adapter"},
        require_confirmation_for=set(),
    )


@pytest.fixture
def mock_secrets():
    """SecretsProvider stub that returns a dummy EAGLE_OSINT_API_KEY."""
    provider = MagicMock()
    provider.get_secret.return_value = "dummy-api-key"
    return provider


@pytest.fixture
def redactor():
    return PiiRedactor()


# ---------------------------------------------------------------------------
# 1. Allowlist / Sensitive-capability registration
# ---------------------------------------------------------------------------


class TestOsintCapabilityRegistration:
    """Verify that osint_search is correctly registered in the authorizer defaults."""

    def test_osint_search_in_default_allowlist(self):
        """osint_search must be present in the default allowlist."""
        assert "osint_search" in _DEFAULT_ALLOWLIST

    def test_eagle_osint_adapter_in_default_allowlist(self):
        """eagle_osint_adapter must be present in the default allowlist."""
        assert "eagle_osint_adapter" in _DEFAULT_ALLOWLIST

    def test_osint_search_in_sensitive_capabilities(self):
        """osint_search must require human confirmation (is a sensitive capability)."""
        assert "osint_search" in _SENSITIVE_CAPABILITIES


# ---------------------------------------------------------------------------
# 2. Authorization enforcement
# ---------------------------------------------------------------------------


class TestOsintAuthorizationEnforcement:
    """Verify that CapabilityAuthorizer blocks osint_search when not confirmed."""

    def test_osint_search_blocked_without_human_confirmation(self, authorizer_with_osint):
        """osint_search must be blocked when human_confirmed is absent."""
        with pytest.raises(PermissionError, match="confirmação humana"):
            authorizer_with_osint.authorize(
                user="alice",
                capability_name="osint_search",
                payload={},
            )

    def test_osint_search_blocked_when_human_confirmed_false(self, authorizer_with_osint):
        """osint_search must be blocked when human_confirmed is explicitly False."""
        with pytest.raises(PermissionError, match="confirmação humana"):
            authorizer_with_osint.authorize(
                user="alice",
                capability_name="osint_search",
                payload={"human_confirmed": False},
            )

    def test_osint_search_passes_with_human_confirmation(self, authorizer_with_osint):
        """osint_search must be authorized when human_confirmed=True."""
        result = authorizer_with_osint.authorize(
            user="alice",
            capability_name="osint_search",
            payload={"human_confirmed": True},
        )
        assert result is True

    def test_osint_search_not_in_allowlist_raises_permission_error(self):
        """If osint_search is not in the allowlist, it must raise PermissionError."""
        authorizer = CapabilityAuthorizer(allowlist={"other_cap"}, require_confirmation_for=set())
        with pytest.raises(PermissionError, match="não está na allowlist"):
            authorizer.authorize(
                user="alice",
                capability_name="osint_search",
                payload={"human_confirmed": True},
            )


# ---------------------------------------------------------------------------
# 3. EagleOsintAdapter — authorization gate
# ---------------------------------------------------------------------------


class TestEagleOsintAdapterAuthorization:
    """Verify that EagleOsintAdapter.execute() respects the CapabilityAuthorizer."""

    def _make_adapter(
        self,
        authorizer: CapabilityAuthorizer,
        mock_secrets,
        redactor: PiiRedactor,
        tmp_path,
    ) -> EagleOsintAdapter:
        return EagleOsintAdapter(
            secrets_provider=mock_secrets,
            pii_redactor=redactor,
            authorizer=authorizer,
            recon_dir=tmp_path,
        )

    def test_execute_blocked_when_no_human_confirmation(
        self, authorizer_with_osint, mock_secrets, redactor, tmp_path
    ):
        """execute() must return success=False when human_confirmed is missing."""
        adapter = self._make_adapter(authorizer_with_osint, mock_secrets, redactor, tmp_path)
        result = adapter.execute({"user": "alice", "query": "target@example.com"})
        assert result["success"] is False
        assert "confirmação humana" in result["error"]

    def test_execute_blocked_when_human_confirmed_false(
        self, authorizer_with_osint, mock_secrets, redactor, tmp_path
    ):
        """execute() must return success=False when human_confirmed=False."""
        adapter = self._make_adapter(authorizer_with_osint, mock_secrets, redactor, tmp_path)
        result = adapter.execute(
            {"user": "alice", "query": "target@example.com", "human_confirmed": False}
        )
        assert result["success"] is False

    def test_execute_blocked_when_capability_not_in_allowlist(
        self, mock_secrets, redactor, tmp_path
    ):
        """execute() must fail when osint_search is absent from the allowlist."""
        strict_authorizer = CapabilityAuthorizer(
            allowlist={"other_cap"}, require_confirmation_for=set()
        )
        adapter = self._make_adapter(strict_authorizer, mock_secrets, redactor, tmp_path)
        result = adapter.execute(
            {"user": "alice", "query": "target@example.com", "human_confirmed": True}
        )
        assert result["success"] is False
        assert "allowlist" in result["error"]

    def test_execute_succeeds_with_confirmed_authorization(
        self, permissive_authorizer, mock_secrets, redactor, tmp_path
    ):
        """execute() must call search and persist when authorization passes."""
        adapter = self._make_adapter(permissive_authorizer, mock_secrets, redactor, tmp_path)
        fake_results = {"profiles": ["user1"], "emails": ["user1@example.com"]}

        with patch.object(adapter, "search", return_value=fake_results):
            result = adapter.execute(
                {"user": "alice", "query": "user1", "human_confirmed": True}
            )

        assert result["success"] is True
        assert "summary" in result
        assert "path" in result

    def test_execute_missing_query_returns_error(
        self, permissive_authorizer, mock_secrets, redactor, tmp_path
    ):
        """execute() must fail gracefully when 'query' is absent."""
        adapter = self._make_adapter(permissive_authorizer, mock_secrets, redactor, tmp_path)
        result = adapter.execute({"user": "alice", "human_confirmed": True})
        assert result["success"] is False
        assert "query" in result["error"]

    def test_execute_handles_search_runtime_error(
        self, permissive_authorizer, mock_secrets, redactor, tmp_path
    ):
        """execute() must return success=False when search() raises RuntimeError."""
        adapter = self._make_adapter(permissive_authorizer, mock_secrets, redactor, tmp_path)

        with patch.object(adapter, "search", side_effect=RuntimeError("API unavailable")):
            result = adapter.execute(
                {"user": "alice", "query": "target", "human_confirmed": True}
            )

        assert result["success"] is False
        assert "API unavailable" in result["error"]


# ---------------------------------------------------------------------------
# 4. PII sanitization in persisted dossier
# ---------------------------------------------------------------------------


class TestOsintPiiSanitization:
    """Verify that PII is redacted before .jrvs persistence."""

    def test_cpf_redacted_in_persisted_dossier(
        self, permissive_authorizer, mock_secrets, redactor, tmp_path
    ):
        """CPF numbers in OSINT results must be redacted in the saved .jrvs file."""
        adapter = EagleOsintAdapter(
            secrets_provider=mock_secrets,
            pii_redactor=redactor,
            authorizer=permissive_authorizer,
            recon_dir=tmp_path,
        )
        raw_results = {"info": "CPF do alvo: 123.456.789-09", "score": 42}

        with patch.object(adapter, "search", return_value=raw_results):
            result = adapter.execute(
                {"user": "analyst", "query": "alvo_cpf", "human_confirmed": True}
            )

        assert result["success"] is True
        saved = jrvs_codec.read_file(result["path"])
        assert "123.456.789-09" not in str(saved)
        assert "[CPF_REDACTED]" in str(saved)

    def test_email_redacted_in_persisted_dossier(
        self, permissive_authorizer, mock_secrets, redactor, tmp_path
    ):
        """Email addresses in OSINT results must be redacted in the saved .jrvs file."""
        adapter = EagleOsintAdapter(
            secrets_provider=mock_secrets,
            pii_redactor=redactor,
            authorizer=permissive_authorizer,
            recon_dir=tmp_path,
        )
        raw_results = {"contact": "john.doe@secret.com", "username": "jdoe"}

        with patch.object(adapter, "search", return_value=raw_results):
            result = adapter.execute(
                {"user": "analyst", "query": "jdoe", "human_confirmed": True}
            )

        assert result["success"] is True
        saved = jrvs_codec.read_file(result["path"])
        assert "john.doe@secret.com" not in str(saved)
        assert "[EMAIL_REDACTED]" in str(saved)
