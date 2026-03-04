# -*- coding: utf-8 -*-
"""Tests for PiiRedactor - PII sanitization before vector indexing."""

import pytest

from app.application.privacy.pii_redactor import PiiRedactor


class TestPiiRedactorSanitize:
    """Unit tests for the sanitize() method."""

    @pytest.fixture
    def redactor(self):
        return PiiRedactor()

    def test_email_is_redacted(self, redactor):
        text = "Meu email é joao.silva@example.com para contato."
        result = redactor.sanitize(text)
        assert "joao.silva@example.com" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_cpf_with_dots_and_dash_is_redacted(self, redactor):
        text = "CPF do usuário: 123.456.789-09"
        result = redactor.sanitize(text)
        assert "123.456.789-09" not in result
        assert "[CPF_REDACTED]" in result

    def test_cpf_digits_only_is_redacted(self, redactor):
        text = "Informe o CPF: 12345678909"
        result = redactor.sanitize(text)
        assert "12345678909" not in result
        assert "[CPF_REDACTED]" in result

    def test_phone_brazilian_is_redacted(self, redactor):
        text = "Ligue para (11) 98765-4321 amanhã."
        result = redactor.sanitize(text)
        assert "98765-4321" not in result
        assert "[PHONE_REDACTED]" in result

    def test_multiple_pii_types_in_same_text(self, redactor):
        text = (
            "Nome: Ana, email: ana@test.org, CPF: 987.654.321-00, "
            "tel: (21) 91234-5678"
        )
        result = redactor.sanitize(text)
        assert "ana@test.org" not in result
        assert "987.654.321-00" not in result
        assert "91234-5678" not in result
        assert "[EMAIL_REDACTED]" in result
        assert "[CPF_REDACTED]" in result
        assert "[PHONE_REDACTED]" in result

    def test_text_without_pii_is_unchanged(self, redactor):
        text = "O assistente abriu o navegador e navegou até o site."
        result = redactor.sanitize(text)
        assert result == text

    def test_empty_string_returns_empty(self, redactor):
        assert redactor.sanitize("") == ""

    def test_none_like_empty_returns_empty(self, redactor):
        # sanitize expects str; passing empty is the boundary case
        assert redactor.sanitize("   ") == "   "

    def test_indexed_text_does_not_contain_email(self, redactor):
        """Verify that text stored after sanitize() contains no raw PII."""
        raw = "Contato: usuario@empresa.com.br"
        sanitized = redactor.sanitize(raw)
        assert "@" not in sanitized or "[EMAIL_REDACTED]" in sanitized

    def test_indexed_text_does_not_contain_cpf(self, redactor):
        raw = "CPF: 111.222.333-44"
        sanitized = redactor.sanitize(raw)
        assert "111.222.333-44" not in sanitized

    def test_indexed_text_does_not_contain_phone(self, redactor):
        raw = "Fone: +55 11 98765-4321"
        sanitized = redactor.sanitize(raw)
        assert "98765-4321" not in sanitized


class TestPiiRedactorPurge:
    """Tests for purge_by_user() and purge_all()."""

    @pytest.fixture
    def redactor(self):
        return PiiRedactor()

    def test_register_and_purge_by_user(self, redactor):
        redactor.register_event("user_1", "evento sem PII", {"channel": "api"})
        redactor.register_event("user_1", "outro evento", {})
        redactor.register_event("user_2", "evento de outro usuário", {})

        removed = redactor.purge_by_user("user_1")

        assert removed == 2
        assert "user_1" not in redactor._user_index
        # user_2 events should remain
        assert "user_2" in redactor._user_index

    def test_purge_by_user_nonexistent_returns_zero(self, redactor):
        removed = redactor.purge_by_user("ghost_user")
        assert removed == 0

    def test_purge_all_removes_everything(self, redactor):
        redactor.register_event("user_a", "texto a", {})
        redactor.register_event("user_b", "texto b", {})

        removed = redactor.purge_all()

        assert removed == 2
        assert redactor._events == {}
        assert redactor._user_index == {}

    def test_purge_all_on_empty_registry_returns_zero(self, redactor):
        assert redactor.purge_all() == 0
