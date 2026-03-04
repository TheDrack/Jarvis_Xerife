# -*- coding: utf-8 -*-
"""Tests for pipeline_runner – Cloud-Mock detection and false-positive prevention."""

import logging
import os
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from app.core.nexus import CloudMock
from app.runtime.pipeline_runner import run_pipeline


def _make_pipeline_config(strict_mode: bool = False) -> str:
    """Return a minimal pipeline YAML string."""
    strict_str = "true" if strict_mode else "false"
    return textwrap.dedent(
        f"""\
        components:
          my_step:
            id: "my_component"
            config:
              strict_mode: {strict_str}
        """
    )


@pytest.fixture
def pipeline_dir(tmp_path):
    """Write pipeline YAML files into a tmp_path-based config tree."""
    cfg_dir = tmp_path / "config" / "pipelines"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "test_pipeline.yml").write_text(_make_pipeline_config())
    (cfg_dir / "test_strict.yml").write_text(_make_pipeline_config(strict_mode=True))
    return tmp_path


class TestCloudMockDetection:
    """pipeline_runner must treat CloudMock as a real failure, not a silent success."""

    def test_cloudmock_skips_execute_and_logs_error(self, pipeline_dir, caplog):
        """When Nexus returns a CloudMock, execute() must NOT be called and an error logged."""
        mock_instance = CloudMock("my_component")
        mock_instance.execute = MagicMock()  # spy to ensure it's not called

        with patch("app.runtime.pipeline_runner.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_instance

            orig_dir = os.getcwd()
            try:
                os.chdir(pipeline_dir)
                with caplog.at_level(logging.ERROR, logger="root"):
                    run_pipeline("test_pipeline")
            finally:
                os.chdir(orig_dir)

        mock_instance.execute.assert_not_called()
        assert any(
            "indisponível" in r.message and "Circuit Breaker" in r.message
            for r in caplog.records
        )

    def test_cloudmock_strict_mode_raises(self, pipeline_dir):
        """In strict mode, a CloudMock return must cause a RuntimeError."""
        mock_instance = CloudMock("my_component")

        with patch("app.runtime.pipeline_runner.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = mock_instance

            orig_dir = os.getcwd()
            try:
                os.chdir(pipeline_dir)
                with pytest.raises(RuntimeError, match="CloudMock"):
                    run_pipeline("test_strict")
            finally:
                os.chdir(orig_dir)

    def test_real_component_executes_normally(self, pipeline_dir):
        """A normal (non-mock) component must be executed and its context returned."""
        real_component = MagicMock()
        real_component.__is_cloud_mock__ = False
        expected_context = {
            "artifacts": {"my_step": "done"},
            "metadata": {"pipeline": "test_pipeline"},
            "env": {},
            "result": {"ok": True},
        }
        real_component.execute.return_value = expected_context

        with patch("app.runtime.pipeline_runner.nexus") as mock_nexus:
            mock_nexus.resolve.return_value = real_component

            orig_dir = os.getcwd()
            try:
                os.chdir(pipeline_dir)
                run_pipeline("test_pipeline")
            finally:
                os.chdir(orig_dir)

        real_component.execute.assert_called_once()
