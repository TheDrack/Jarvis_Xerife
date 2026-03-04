# -*- coding: utf-8 -*-
"""Tests that verify all new security components follow repository rules.

Rules verified:
- All new components implement the NexusComponent contract (execute() method).
- Components are resolvable via nexus.resolve().
- VectorMemoryAdapter sanitizes PII before indexing (PiiRedactor integration).
- CapabilityAuthorizer.execute() follows the NexusComponent return contract.
- PiiRedactor.execute() follows the NexusComponent return contract.
- EnvSecretsProvider.execute() follows the NexusComponent return contract.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.application.privacy.pii_redactor import PiiRedactor
from app.application.security.capability_authorizer import CapabilityAuthorizer
from app.adapters.infrastructure.secrets.env_secrets_provider import EnvSecretsProvider
from app.adapters.infrastructure.vector_memory_adapter import VectorMemoryAdapter
from app.core.nexuscomponent import NexusComponent


# ---------------------------------------------------------------------------
# 1. NexusComponent contract compliance
# ---------------------------------------------------------------------------

class TestNexusComponentContract:
    """All new security/privacy components must implement NexusComponent."""

    def test_capability_authorizer_is_nexus_component(self):
        authorizer = CapabilityAuthorizer()
        assert isinstance(authorizer, NexusComponent)

    def test_pii_redactor_is_nexus_component(self):
        redactor = PiiRedactor()
        assert isinstance(redactor, NexusComponent)

    def test_env_secrets_provider_is_nexus_component(self):
        provider = EnvSecretsProvider()
        assert isinstance(provider, NexusComponent)

    def test_capability_authorizer_has_execute(self):
        authorizer = CapabilityAuthorizer()
        assert callable(getattr(authorizer, "execute", None))

    def test_pii_redactor_has_execute(self):
        redactor = PiiRedactor()
        assert callable(getattr(redactor, "execute", None))

    def test_env_secrets_provider_has_execute(self):
        provider = EnvSecretsProvider()
        assert callable(getattr(provider, "execute", None))


# ---------------------------------------------------------------------------
# 2. execute() return contract — must return dict with 'success' key
# ---------------------------------------------------------------------------

class TestExecuteReturnContract:
    """execute() must always return a dict containing the 'success' key."""

    def test_capability_authorizer_execute_returns_dict_with_success(self):
        authorizer = CapabilityAuthorizer(
            allowlist={"safe_cap"}, require_confirmation_for=set()
        )
        result = authorizer.execute({"user": "u", "capability_name": "safe_cap", "payload": {}})
        assert isinstance(result, dict)
        assert "success" in result

    def test_capability_authorizer_execute_authorized_returns_success_true(self):
        authorizer = CapabilityAuthorizer(
            allowlist={"safe_cap"}, require_confirmation_for=set()
        )
        result = authorizer.execute({"user": "u", "capability_name": "safe_cap"})
        assert result["success"] is True
        assert result.get("authorized") is True

    def test_capability_authorizer_execute_unknown_cap_returns_success_false(self):
        authorizer = CapabilityAuthorizer(allowlist=set())
        result = authorizer.execute({"user": "u", "capability_name": "bad_cap"})
        assert result["success"] is False
        assert "error" in result

    def test_capability_authorizer_execute_missing_capability_name_returns_error(self):
        authorizer = CapabilityAuthorizer()
        result = authorizer.execute({})
        assert result["success"] is False

    def test_pii_redactor_execute_sanitize_returns_dict_with_success(self):
        redactor = PiiRedactor()
        result = redactor.execute({"text": "hello world"})
        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is True
        assert "result" in result

    def test_pii_redactor_execute_missing_text_returns_error(self):
        redactor = PiiRedactor()
        result = redactor.execute({})
        assert result["success"] is False

    def test_pii_redactor_execute_purge_all_returns_dict(self):
        redactor = PiiRedactor()
        result = redactor.execute({"action": "purge_all"})
        assert result["success"] is True
        assert "purged" in result

    def test_pii_redactor_execute_purge_by_user_returns_dict(self):
        redactor = PiiRedactor()
        redactor.register_event("user_x", "texto")
        result = redactor.execute({"action": "purge_by_user", "user_id": "user_x"})
        assert result["success"] is True
        assert result["purged"] == 1

    def test_pii_redactor_execute_unknown_action_returns_error(self):
        redactor = PiiRedactor()
        result = redactor.execute({"action": "unknown"})
        assert result["success"] is False

    def test_env_secrets_provider_execute_missing_key_returns_error(self):
        provider = EnvSecretsProvider()
        result = provider.execute({})
        assert result["success"] is False

    def test_env_secrets_provider_execute_existing_key_returns_value(self):
        provider = EnvSecretsProvider()
        with patch.dict(os.environ, {"TEST_SECRET_XYZ": "mysecret"}):
            result = provider.execute({"key": "TEST_SECRET_XYZ"})
        assert result["success"] is True
        assert result["value"] == "mysecret"

    def test_env_secrets_provider_execute_missing_env_var_returns_error(self):
        provider = EnvSecretsProvider()
        os.environ.pop("NONEXISTENT_VAR_ABC", None)
        result = provider.execute({"key": "NONEXISTENT_VAR_ABC"})
        assert result["success"] is False


# ---------------------------------------------------------------------------
# 3. nexus.resolve() — components must be discoverable by the Nexus
# ---------------------------------------------------------------------------

class TestNexusResolvability:
    """New components must be resolvable via nexus.resolve()."""

    def test_capability_authorizer_resolvable(self):
        from app.core.nexus import nexus
        instance = nexus.resolve("capability_authorizer")
        assert instance is not None
        assert isinstance(instance, CapabilityAuthorizer)

    def test_pii_redactor_resolvable(self):
        from app.core.nexus import nexus
        instance = nexus.resolve("pii_redactor")
        assert instance is not None
        assert isinstance(instance, PiiRedactor)

    def test_env_secrets_provider_resolvable(self):
        from app.core.nexus import nexus
        instance = nexus.resolve("env_secrets_provider")
        assert instance is not None
        assert isinstance(instance, EnvSecretsProvider)


# ---------------------------------------------------------------------------
# 4. VectorMemoryAdapter PII integration
# ---------------------------------------------------------------------------

class TestVectorMemoryPiiIntegration:
    """VectorMemoryAdapter must sanitize PII before indexing via PiiRedactor."""

    @pytest.fixture
    def adapter_with_redactor(self):
        """VectorMemoryAdapter wired with a real PiiRedactor (no FAISS)."""
        import app.adapters.infrastructure.vector_memory_adapter as mod

        original = mod._FAISS_AVAILABLE
        mod._FAISS_AVAILABLE = False
        a = VectorMemoryAdapter(dim=64)
        a._index = None
        # Inject a real PiiRedactor directly (bypasses Nexus for isolation)
        a._pii_redactor = PiiRedactor()
        yield a
        mod._FAISS_AVAILABLE = original

    def test_email_is_not_stored_raw(self, adapter_with_redactor):
        adapter_with_redactor.store_event("Contato: usuario@empresa.com.br")
        stored_text = adapter_with_redactor._events[0]["text"]
        assert "usuario@empresa.com.br" not in stored_text
        assert "[EMAIL_REDACTED]" in stored_text

    def test_cpf_is_not_stored_raw(self, adapter_with_redactor):
        adapter_with_redactor.store_event("CPF: 123.456.789-09")
        stored_text = adapter_with_redactor._events[0]["text"]
        assert "123.456.789-09" not in stored_text
        assert "[CPF_REDACTED]" in stored_text

    def test_phone_is_not_stored_raw(self, adapter_with_redactor):
        adapter_with_redactor.store_event("Tel: (11) 98765-4321")
        stored_text = adapter_with_redactor._events[0]["text"]
        assert "98765-4321" not in stored_text
        assert "[PHONE_REDACTED]" in stored_text

    def test_clean_text_stored_unchanged(self, adapter_with_redactor):
        clean = "O assistente abriu o navegador."
        adapter_with_redactor.store_event(clean)
        stored_text = adapter_with_redactor._events[0]["text"]
        assert stored_text == clean

    def test_pii_redactor_resolves_via_nexus_in_adapter(self):
        """When no redactor is injected, the adapter tries Nexus resolution."""
        import app.adapters.infrastructure.vector_memory_adapter as mod

        original = mod._FAISS_AVAILABLE
        mod._FAISS_AVAILABLE = False
        try:
            a = VectorMemoryAdapter(dim=64)
            a._index = None
            # _pii_redactor is None — Nexus will be called on first store_event
            mock_redactor = MagicMock()
            mock_redactor.sanitize = MagicMock(return_value="texto seguro")

            with patch("app.core.nexus.nexus.resolve", return_value=mock_redactor) as mock_resolve:
                a.store_event("texto qualquer")
                mock_resolve.assert_called_once_with("pii_redactor")
                mock_redactor.sanitize.assert_called_once_with("texto qualquer")
        finally:
            mod._FAISS_AVAILABLE = original
