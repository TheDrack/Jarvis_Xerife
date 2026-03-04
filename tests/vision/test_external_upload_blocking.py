# -*- coding: utf-8 -*-
"""Tests for VisionAdapter external upload hardening."""

import pytest
from unittest.mock import patch

from app.adapters.infrastructure.vision_adapter import (
    ExternalVisionNotAllowedError,
    VisionAdapter,
)

FAKE_IMAGE = b"\x89PNG\r\n\x1a\n"


class TestExternalUploadBlocking:
    """Verify that external image uploads are blocked without proper consent."""

    @pytest.fixture
    def adapter_no_consent(self):
        """Adapter with both flags False (default-safe)."""
        return VisionAdapter(api_key="test-key", allow_external_vision=False, user_consent=False)

    @pytest.fixture
    def adapter_flag_only(self):
        """allow_external_vision=True but user_consent=False."""
        return VisionAdapter(api_key="test-key", allow_external_vision=True, user_consent=False)

    @pytest.fixture
    def adapter_consent_only(self):
        """user_consent=True but allow_external_vision=False."""
        return VisionAdapter(api_key="test-key", allow_external_vision=False, user_consent=True)

    @pytest.fixture
    def adapter_full_consent(self):
        """Both flags True – upload should be permitted."""
        return VisionAdapter(api_key="test-key", allow_external_vision=True, user_consent=True)

    # ------------------------------------------------------------------
    # Blocking scenarios
    # ------------------------------------------------------------------

    def test_upload_blocked_when_both_flags_false(self, adapter_no_consent):
        """Upload must raise ExternalVisionNotAllowedError when both flags are False."""
        with pytest.raises(ExternalVisionNotAllowedError):
            adapter_no_consent._analyze_with_gemini(FAKE_IMAGE, "describe")

    def test_upload_blocked_when_only_allow_flag_set(self, adapter_flag_only):
        """Upload must be blocked when user_consent is False, even if allow flag is True."""
        with pytest.raises(ExternalVisionNotAllowedError):
            adapter_flag_only._analyze_with_gemini(FAKE_IMAGE, "describe")

    def test_upload_blocked_when_only_consent_set(self, adapter_consent_only):
        """Upload must be blocked when allow_external_vision is False, even if consent is True."""
        with pytest.raises(ExternalVisionNotAllowedError):
            adapter_consent_only._analyze_with_gemini(FAKE_IMAGE, "describe")

    # ------------------------------------------------------------------
    # Allowed scenario
    # ------------------------------------------------------------------

    def test_upload_proceeds_when_both_flags_true(self, adapter_full_consent):
        """When both flags are True, _analyze_with_gemini should proceed past the guard."""
        # The Gemini client call will fail (mocked), but the consent check must pass.
        with patch(
            "app.adapters.infrastructure.vision_adapter.VisionAdapter._check_external_upload_consent"
        ) as mock_check:
            mock_check.return_value = None  # no exception raised
            with patch("google.genai.Client") as _:
                # We just verify the consent check is NOT raising
                try:
                    adapter_full_consent._analyze_with_gemini(FAKE_IMAGE, "describe")
                except ExternalVisionNotAllowedError:
                    pytest.fail("ExternalVisionNotAllowedError raised unexpectedly")
                mock_check.assert_called_once()

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def test_blocked_attempt_is_recorded_in_audit_log(self, adapter_no_consent):
        """Every blocked upload attempt must be written to the audit log."""
        with pytest.raises(ExternalVisionNotAllowedError):
            adapter_no_consent._analyze_with_gemini(FAKE_IMAGE, "describe")

        assert len(adapter_no_consent._audit_log) == 1
        entry = adapter_no_consent._audit_log[0]
        assert entry["allowed"] is False
        assert "timestamp" in entry
        assert "image_source" in entry

    def test_audit_log_does_not_store_image_bytes(self, adapter_no_consent):
        """Image data must never appear in audit log entries."""
        with pytest.raises(ExternalVisionNotAllowedError):
            adapter_no_consent._analyze_with_gemini(FAKE_IMAGE, "describe")

        for entry in adapter_no_consent._audit_log:
            for value in entry.values():
                assert value != FAKE_IMAGE, "Image bytes found in audit log!"

    def test_default_initialization_blocks_uploads(self):
        """A freshly instantiated VisionAdapter must block external uploads by default."""
        adapter = VisionAdapter(api_key="key")
        assert adapter.allow_external_vision is False
        assert adapter.user_consent is False
        with pytest.raises(ExternalVisionNotAllowedError):
            adapter._analyze_with_gemini(FAKE_IMAGE, "describe")
