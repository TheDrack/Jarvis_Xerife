# -*- coding: utf-8 -*-
"""Tests for Nexus ↔ Gist ↔ nexus_registry.json sync behavior"""

import json
import os
from unittest.mock import MagicMock, patch, mock_open

import pytest


class TestNexusRegistrySync:
    """Tests for JarvisNexus local registry seeding and sync."""

    def _make_nexus(self, base_dir="/fake/base"):
        """Helper: create a bare JarvisNexus instance for unit-testing individual methods."""
        from app.core.nexus import JarvisNexus
        nexus = JarvisNexus.__new__(JarvisNexus)
        nexus.gist_id = "test_gist_id"
        nexus.base_dir = base_dir
        return nexus

    def test_load_local_registry_converts_full_path_to_module(self):
        """_load_local_registry should strip ClassName from the stored path."""
        from app.core.nexus import JarvisNexus

        registry_data = {
            "components": {
                "audit_logger": "app.adapters.infrastructure.audit_logger.AuditLogger",
                "cognitive_router": "app.domain.gears.cognitive_router.CognitiveRouter",
            }
        }
        nexus = JarvisNexus.__new__(JarvisNexus)
        nexus.base_dir = "/fake"

        with patch("builtins.open", mock_open(read_data=json.dumps(registry_data))):
            result = nexus._load_local_registry()

        assert result["audit_logger"] == "app.adapters.infrastructure.audit_logger"
        assert result["cognitive_router"] == "app.domain.gears.cognitive_router"

    def test_load_local_registry_returns_empty_on_missing_file(self):
        """_load_local_registry should return {} when file not found."""
        from app.core.nexus import JarvisNexus

        nexus = JarvisNexus.__new__(JarvisNexus)
        nexus.base_dir = "/fake"

        with patch("builtins.open", side_effect=FileNotFoundError("not found")):
            result = nexus._load_local_registry()

        assert result == {}

    def test_cache_seeded_from_local_when_gist_fails(self):
        """Cache should be populated from local registry when Gist is unavailable."""
        from app.core.nexus import JarvisNexus

        registry_data = {
            "components": {
                "audit_logger": "app.adapters.infrastructure.audit_logger.AuditLogger"
            }
        }
        mock_gist_response = MagicMock()
        mock_gist_response.status_code = 500

        with patch("builtins.open", mock_open(read_data=json.dumps(registry_data))), \
             patch("requests.get", return_value=mock_gist_response):
            nexus = JarvisNexus.__new__(JarvisNexus)
            nexus.gist_id = "test_id"
            nexus.base_dir = "/fake"
            nexus._instances = {}
            local = nexus._load_local_registry()
            remote = nexus._load_remote_memory()
            nexus._cache = {**local, **remote}
            nexus._mutated = bool(set(local.keys()) - set(remote.keys()))

        assert nexus._cache["audit_logger"] == "app.adapters.infrastructure.audit_logger"
        assert nexus._mutated is True  # local has entries not in remote → push to Gist

    def test_cache_gist_takes_precedence_over_local(self):
        """Gist data should override local registry when both have the same key."""
        from app.core.nexus import JarvisNexus

        registry_data = {
            "components": {
                "audit_logger": "app.adapters.infrastructure.OLD_path.AuditLogger"
            }
        }
        gist_data = {
            "audit_logger": "app.adapters.infrastructure.audit_logger"
        }
        mock_gist_response = MagicMock()
        mock_gist_response.status_code = 200
        mock_gist_response.json.return_value = gist_data

        with patch("builtins.open", mock_open(read_data=json.dumps(registry_data))), \
             patch("requests.get", return_value=mock_gist_response):
            nexus = JarvisNexus.__new__(JarvisNexus)
            nexus.gist_id = "test_id"
            nexus.base_dir = "/fake"
            nexus._instances = {}
            local = nexus._load_local_registry()
            remote = nexus._load_remote_memory()
            nexus._cache = {**local, **remote}

        assert nexus._cache["audit_logger"] == "app.adapters.infrastructure.audit_logger"

    def test_not_mutated_when_local_subset_of_gist(self):
        """_mutated should be False when local registry has no entries missing from Gist."""
        from app.core.nexus import JarvisNexus

        registry_data = {
            "components": {
                "audit_logger": "app.adapters.infrastructure.audit_logger.AuditLogger"
            }
        }
        gist_data = {
            "audit_logger": "app.adapters.infrastructure.audit_logger",
            "llm_engine": "app.domain.gears.llm_engine",
        }
        mock_gist_response = MagicMock()
        mock_gist_response.status_code = 200
        mock_gist_response.json.return_value = gist_data

        with patch("builtins.open", mock_open(read_data=json.dumps(registry_data))), \
             patch("requests.get", return_value=mock_gist_response):
            nexus = JarvisNexus.__new__(JarvisNexus)
            nexus.gist_id = "test_id"
            nexus.base_dir = "/fake"
            nexus._instances = {}
            local = nexus._load_local_registry()
            remote = nexus._load_remote_memory()
            nexus._cache = {**local, **remote}
            nexus._mutated = bool(set(local.keys()) - set(remote.keys()))

        assert nexus._mutated is False

    def test_update_local_registry_writes_full_class_path(self):
        """_update_local_registry should write module.ClassName format."""
        from app.core.nexus import JarvisNexus

        nexus = JarvisNexus.__new__(JarvisNexus)
        nexus.base_dir = "/fake"
        nexus._cache = {
            "audit_logger": "app.adapters.infrastructure.audit_logger",
            "cognitive_router": "app.domain.gears.cognitive_router",
        }

        captured = {}

        def capture_dump(data, f, **kwargs):
            captured.update(data)

        with patch("json.dump", side_effect=capture_dump), \
             patch("builtins.open", mock_open()):
            nexus._update_local_registry()

        assert "components" in captured
        assert captured["components"]["audit_logger"] == "app.adapters.infrastructure.audit_logger.AuditLogger"
        assert captured["components"]["cognitive_router"] == "app.domain.gears.cognitive_router.CognitiveRouter"

    def test_commit_memory_updates_registry_on_success(self):
        """commit_memory should call _update_local_registry after a successful Gist update."""
        from app.core.nexus import JarvisNexus

        nexus = JarvisNexus.__new__(JarvisNexus)
        nexus.gist_id = "test_id"
        nexus._cache = {"audit_logger": "app.adapters.infrastructure.audit_logger"}
        nexus._mutated = True

        mock_patch_response = MagicMock()
        mock_patch_response.status_code = 200

        with patch.dict(os.environ, {"GIST_PAT": "fake_token"}), \
             patch("requests.patch", return_value=mock_patch_response), \
             patch.object(nexus, "_update_local_registry") as mock_update:
            nexus.commit_memory()

        mock_update.assert_called_once()
        assert nexus._mutated is False

    def test_commit_memory_does_not_update_registry_on_failure(self):
        """commit_memory should NOT call _update_local_registry if Gist update fails."""
        from app.core.nexus import JarvisNexus

        nexus = JarvisNexus.__new__(JarvisNexus)
        nexus.gist_id = "test_id"
        nexus._cache = {"audit_logger": "app.adapters.infrastructure.audit_logger"}
        nexus._mutated = True

        mock_patch_response = MagicMock()
        mock_patch_response.status_code = 422  # failure

        with patch.dict(os.environ, {"GIST_PAT": "fake_token"}), \
             patch("requests.patch", return_value=mock_patch_response), \
             patch.object(nexus, "_update_local_registry") as mock_update:
            nexus.commit_memory()

        mock_update.assert_not_called()
        assert nexus._mutated is True  # still dirty
