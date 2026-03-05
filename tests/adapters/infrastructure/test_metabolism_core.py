# -*- coding: utf-8 -*-
"""
Tests for MetabolismCore multi-LLM client.

Covers the fixes applied to address CI failures:
  1. gemini-2.0-flash-exp → gemini-2.0-flash (HTTP 404 fix)
  2. _safe_json_decode handling empty/truncated content (DNA corrupted fix)
  3. Per-provider rate-limit cooldown (HTTP 429 skipping fix)
  4. Fallback continues past rate-limited providers
"""
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

import app.application.services.metabolism_core as mc_module
from app.application.services.metabolism_core import MetabolismCore, RateLimitError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resp(status: int, json_body: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.text = text
    if json_body is not None:
        resp.json.return_value = json_body
    return resp


def _openai_ok(content: str) -> MagicMock:
    return _make_resp(200, {"choices": [{"message": {"content": content}}]})


# ---------------------------------------------------------------------------
# Model fleet configuration
# ---------------------------------------------------------------------------


class TestFleetConfiguration:
    """Fleet must contain the stable gemini-2.0-flash (not the deprecated -exp variant)."""

    def test_gemini_model_is_stable(self):
        names = [p["name"] for p in MetabolismCore._FLEET]
        assert "google/gemini-2.0-flash" in names, "gemini-2.0-flash deve estar na frota"

    def test_deprecated_gemini_exp_removed(self):
        names = [p["name"] for p in MetabolismCore._FLEET]
        assert "google/gemini-2.0-flash-exp" not in names, (
            "gemini-2.0-flash-exp foi descontinuado e não deve estar na frota"
        )

    def test_gemini_url_does_not_contain_exp(self):
        for p in MetabolismCore._FLEET:
            if p.get("type") == "gemini":
                assert "-exp" not in p["url"], (
                    f"URL Gemini não deve referenciar modelo experimental: {p['url']}"
                )


# ---------------------------------------------------------------------------
# _safe_json_decode
# ---------------------------------------------------------------------------


class TestSafeJsonDecode:
    """Robust JSON extraction from LLM responses."""

    def setup_method(self):
        self.core = MetabolismCore()

    def test_valid_json(self):
        result = self.core._safe_json_decode('{"code": "x", "summary": "ok"}')
        assert result == {"code": "x", "summary": "ok"}

    def test_markdown_wrapped_json(self):
        result = self.core._safe_json_decode('```json\n{"code": "x"}\n```')
        assert result == {"code": "x"}

    def test_json_with_surrounding_text(self):
        result = self.core._safe_json_decode('Here is: {"code": "x"} done.')
        assert result == {"code": "x"}

    def test_empty_string_raises(self):
        with pytest.raises(Exception, match="conteúdo vazio"):
            self.core._safe_json_decode("")

    def test_whitespace_only_raises(self):
        with pytest.raises(Exception, match="conteúdo vazio"):
            self.core._safe_json_decode("   \n  ")

    def test_invalid_json_raises_dna_corrupted(self):
        with pytest.raises(Exception, match="DNA corrompido"):
            self.core._safe_json_decode("this is not json at all !!!")


# ---------------------------------------------------------------------------
# Rate-limit cooldown
# ---------------------------------------------------------------------------


class TestRateLimitCooldown:
    """Providers in cooldown must be skipped until the window expires."""

    def setup_method(self):
        # Clear any stale cooldowns from other tests
        mc_module._RATE_LIMIT_COOLDOWN.clear()

    def teardown_method(self):
        mc_module._RATE_LIMIT_COOLDOWN.clear()

    def test_rate_limited_provider_is_skipped(self):
        core = MetabolismCore()
        # Simulate groq/llama-3.3-70b-versatile in cooldown
        mc_module._RATE_LIMIT_COOLDOWN["groq/llama-3.3-70b-versatile"] = time.time() + 60

        call_count = {"n": 0}

        def fake_post(url, **kwargs):
            call_count["n"] += 1
            # Second provider (gemini) — return valid json
            return _make_resp(
                200,
                {
                    "candidates": [
                        {"content": {"parts": [{"text": '{"code":"x","summary":"ok"}'}]}}
                    ]
                },
            )

        with patch.dict("os.environ", {"GROQ_API_KEY": "key", "GEMINI_API_KEY": "key"}):
            with patch("requests.post", side_effect=fake_post):
                result = core.ask_jarvis("sys", "user", require_json=True)

        # Only one HTTP call (the gemini one), groq was skipped
        assert call_count["n"] == 1

    def test_rate_limit_error_sets_cooldown(self):
        core = MetabolismCore()

        responses = [
            _make_resp(429),  # groq/llama-3.3-70b-versatile → 429
            _openai_ok('{"ok": true}'),  # groq/llama-3.1-8b-instant succeeds
        ]
        resp_iter = iter(responses)

        # Only enable GROQ_API_KEY; blank out other providers so they're skipped.
        # Flow: llama-3.3-70b-versatile → 429 → cooldown; llama-3.1-8b-instant → ok
        with patch.dict(
            "os.environ",
            {
                "GROQ_API_KEY": "key",
                "GEMINI_API_KEY": "",
                "OPENROUTER_API_KEY": "",
                "MISTRAL_API_KEY": "",
            },
        ):
            with patch("requests.post", side_effect=lambda *a, **kw: next(resp_iter)):
                result = core.ask_jarvis("sys", "user", require_json=True)

        assert result == {"ok": True}
        assert "groq/llama-3.3-70b-versatile" in mc_module._RATE_LIMIT_COOLDOWN

    def test_cooldown_expires_and_provider_retried(self):
        """After cooldown expires the provider should be tried again."""
        core = MetabolismCore()
        # Set cooldown in the past (already expired)
        mc_module._RATE_LIMIT_COOLDOWN["groq/llama-3.3-70b-versatile"] = time.time() - 1

        with patch.dict("os.environ", {"GROQ_API_KEY": "key"}):
            with patch("requests.post", return_value=_openai_ok('{"result": 1}')):
                result = core.ask_jarvis("sys", "user", require_json=True)

        assert result == {"result": 1}


# ---------------------------------------------------------------------------
# ask_jarvis fallback
# ---------------------------------------------------------------------------


class TestAskJarvisFallback:
    """ask_jarvis should fall through to the next available provider on errors."""

    def setup_method(self):
        mc_module._RATE_LIMIT_COOLDOWN.clear()

    def teardown_method(self):
        mc_module._RATE_LIMIT_COOLDOWN.clear()

    def test_falls_through_to_second_provider(self):
        core = MetabolismCore()
        responses = [
            _make_resp(500, text="Server error"),  # first provider fails
            _make_resp(
                200,
                {
                    "candidates": [
                        {"content": {"parts": [{"text": '{"answer": "42"}'}]}}
                    ]
                },
            ),  # second provider (gemini) succeeds
        ]
        resp_iter = iter(responses)

        with patch.dict("os.environ", {"GROQ_API_KEY": "key", "GEMINI_API_KEY": "key"}):
            with patch("requests.post", side_effect=lambda *a, **kw: next(resp_iter)):
                result = core.ask_jarvis("sys", "user", require_json=True)

        assert result == {"answer": "42"}

    def test_all_providers_fail_raises(self):
        core = MetabolismCore()
        with patch.dict("os.environ", {"GROQ_API_KEY": "key"}):
            with patch("requests.post", return_value=_make_resp(500, text="err")):
                with pytest.raises(Exception, match="Todos os provedores falharam"):
                    core.ask_jarvis("sys", "user")
