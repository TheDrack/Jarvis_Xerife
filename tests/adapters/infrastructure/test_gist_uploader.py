# -*- coding: utf-8 -*-
"""Tests for GistUploader – GitHub Gist DNA backup adapter."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.adapters.infrastructure.gist_uploader import GistUploader


def _make_context(file_path: str = None) -> dict:
    ctx: dict = {"artifacts": {}, "metadata": {}, "result": {}}
    if file_path:
        ctx["result"] = {"status": "success", "file_path": file_path}
        ctx["artifacts"]["consolidator"] = {"status": "success", "file_path": file_path}
    return ctx


def _mock_response(status_code: int, json_data: dict = None):
    resp = Mock()
    resp.status_code = status_code
    resp.json = Mock(return_value=json_data or {})
    resp.text = str(json_data or {})
    return resp


class TestGistUploaderInit:
    def test_reads_token_from_env(self):
        with patch.dict(os.environ, {"GIST_PAT": "ghp_test123"}):
            uploader = GistUploader()
        assert uploader.token == "ghp_test123"

    def test_has_fixed_gist_id(self):
        uploader = GistUploader()
        assert uploader.gist_id == "8e8af66f7a65c36881348ff7936ad8b8"

    def test_missing_token_is_none(self):
        env = {k: v for k, v in os.environ.items() if k != "GIST_PAT"}
        with patch.dict(os.environ, env, clear=True):
            uploader = GistUploader()
        assert uploader.token is None


class TestGistUploaderExecute:
    def test_missing_file_path_returns_context(self):
        uploader = GistUploader()
        uploader.token = "ghp_test"
        ctx = _make_context()
        result = uploader.execute(ctx)
        assert result is ctx

    def test_nonexistent_file_returns_context(self, tmp_path):
        uploader = GistUploader()
        uploader.token = "ghp_test"
        ctx = _make_context(file_path=str(tmp_path / "nonexistent.txt"))
        result = uploader.execute(ctx)
        assert result is ctx

    def test_missing_token_returns_context(self, tmp_path):
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("DNA content", encoding="utf-8")

        env = {k: v for k, v in os.environ.items() if k != "GIST_PAT"}
        with patch.dict(os.environ, env, clear=True):
            uploader = GistUploader()

        ctx = _make_context(file_path=str(backup_file))
        result = uploader.execute(ctx)
        assert result is ctx

    def test_successful_patch_updates_artifact(self, tmp_path):
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("DNA content", encoding="utf-8")

        mock_resp = _mock_response(200, {"html_url": "https://gist.github.com/test"})

        with patch("app.adapters.infrastructure.gist_uploader.requests.patch", return_value=mock_resp):
            uploader = GistUploader()
            uploader.token = "ghp_test"
            ctx = _make_context(file_path=str(backup_file))
            result = uploader.execute(ctx)

        assert result["artifacts"]["gist_backup"]["status"] == "updated"
        assert result["artifacts"]["gist_backup"]["url"] == "https://gist.github.com/test"

    def test_gist_not_found_falls_back_to_post(self, tmp_path):
        """A 404 on PATCH should trigger a fallback POST to create a new Gist."""
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("DNA content", encoding="utf-8")

        mock_404 = _mock_response(404, {})
        mock_201 = _mock_response(201, {"html_url": "https://gist.github.com/new"})

        with patch("app.adapters.infrastructure.gist_uploader.requests.patch", return_value=mock_404):
            with patch("app.adapters.infrastructure.gist_uploader.requests.post", return_value=mock_201):
                uploader = GistUploader()
                uploader.token = "ghp_test"
                ctx = _make_context(file_path=str(backup_file))
                result = uploader.execute(ctx)

        assert result["artifacts"]["gist_backup"]["status"] == "created"
        assert result["artifacts"]["gist_backup"]["url"] == "https://gist.github.com/new"

    def test_api_error_logs_but_returns_context(self, tmp_path):
        """A non-200/404 API response should be logged but not raise."""
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("DNA content", encoding="utf-8")

        mock_resp = _mock_response(500, {"error": "Internal Server Error"})

        with patch("app.adapters.infrastructure.gist_uploader.requests.patch", return_value=mock_resp):
            uploader = GistUploader()
            uploader.token = "ghp_test"
            ctx = _make_context(file_path=str(backup_file))
            result = uploader.execute(ctx)

        assert result is ctx
        assert "gist_backup" not in result["artifacts"]

    def test_network_exception_returns_context(self, tmp_path):
        """Network errors should be caught and context returned unchanged."""
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("DNA content", encoding="utf-8")

        with patch(
            "app.adapters.infrastructure.gist_uploader.requests.patch",
            side_effect=ConnectionError("Network unreachable"),
        ):
            uploader = GistUploader()
            uploader.token = "ghp_test"
            ctx = _make_context(file_path=str(backup_file))
            result = uploader.execute(ctx)

        assert result is ctx

    def test_file_path_from_consolidator_artifact_fallback(self, tmp_path):
        """When result has no file_path, falls back to consolidator artifact."""
        backup_file = tmp_path / "backup.txt"
        backup_file.write_text("DNA content", encoding="utf-8")

        mock_resp = _mock_response(200, {"html_url": "https://gist.github.com/test"})

        with patch("app.adapters.infrastructure.gist_uploader.requests.patch", return_value=mock_resp):
            uploader = GistUploader()
            uploader.token = "ghp_test"
            ctx = {
                "artifacts": {"consolidator": {"file_path": str(backup_file)}},
                "metadata": {},
                "result": {},
            }
            result = uploader.execute(ctx)

        assert result["artifacts"]["gist_backup"]["status"] == "updated"
