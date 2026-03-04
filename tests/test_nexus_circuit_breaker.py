# -*- coding: utf-8 -*-
"""Tests for JarvisNexus - Circuit Breaker and CloudMock validation"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.core.nexus import (
    AmbiguousComponentError,
    CloudMock,
    JarvisNexus,
    _CIRCUIT_BREAKER_RESET,
)


class TestCloudMock:
    """Tests for the CloudMock fallback component."""

    def test_execute_preserves_context(self):
        mock = CloudMock("test_component")
        ctx = {"artifacts": {"prev": "data"}, "metadata": {"pipeline": "test"}, "result": {}}
        result = mock.execute(ctx)
        # The original context must be returned intact (with fallback info merged into result)
        assert result is ctx
        assert result["artifacts"]["prev"] == "data"
        assert result["result"]["fallback"] is True
        assert result["result"]["component"] == "test_component"

    def test_execute_without_context_returns_fallback_dict(self):
        mock = CloudMock("test_component")
        result = mock.execute()
        assert result["fallback"] is True
        assert result["component"] == "test_component"

    def test_unknown_method_returns_callable(self):
        mock = CloudMock("my_svc")
        method = mock.some_method
        assert callable(method)
        result = method("arg1", key="val")
        assert result is None


class TestJarvisNexusCircuitBreaker:
    """Tests for the Nexus Circuit Breaker mechanism."""

    def test_circuit_opens_after_timeout(self):
        """When instantiation hangs, Nexus should inject CloudMock and open circuit."""
        nexus = JarvisNexus()

        def _slow_resolve(target_id, hint_path=None):
            time.sleep(10)  # much longer than 2 s timeout
            return None

        with patch.object(nexus, "_resolve_internal", side_effect=_slow_resolve):
            result = nexus.resolve("slow_component")

        assert isinstance(result, CloudMock)
        assert "slow_component" in nexus._circuit_breaker

    def test_circuit_returns_mock_while_open(self):
        """While circuit is open, resolve() should immediately return CloudMock."""
        nexus = JarvisNexus()
        nexus._open_circuit("broken_svc", "test failure")

        result = nexus.resolve("broken_svc")
        assert isinstance(result, CloudMock)

    def test_circuit_resets_after_cooling_off(self):
        """After _CIRCUIT_BREAKER_RESET seconds, the circuit should be closed again."""
        nexus = JarvisNexus()
        nexus._open_circuit("aging_svc", "old failure")

        # Simulate time passing beyond the reset window
        entry = nexus._circuit_breaker["aging_svc"]
        entry.open_at -= _CIRCUIT_BREAKER_RESET + 1

        # Now the circuit should be considered closed
        is_open = nexus._is_circuit_open("aging_svc")
        assert is_open is False
        assert "aging_svc" not in nexus._circuit_breaker  # entry cleaned up

    def test_successful_resolve_caches_instance(self):
        """A successfully resolved component should be cached in _instances."""
        nexus = JarvisNexus()

        class FakeSvc:
            pass

        def _fast_resolve(target_id, hint_path=None):
            return FakeSvc()

        with patch.object(nexus, "_resolve_internal", side_effect=_fast_resolve):
            instance1 = nexus.resolve("fast_svc")
            instance2 = nexus.resolve("fast_svc")

        assert instance1 is instance2  # same cached instance

    def test_resolve_returns_none_for_unknown_component(self):
        """If nothing is found and no timeout occurs, resolve returns None."""
        nexus = JarvisNexus()
        # Don't walk the disk — patch internal search to return nothing fast
        with patch.object(nexus, "_resolve_internal", return_value=None):
            result = nexus.resolve("nonexistent_xyz_abc")
        assert result is None


class TestThreadSafeResolve:
    """Tests for double-checked locking and single-instance guarantee."""

    def test_thread_safe_resolve_creates_single_instance(self):
        """Concurrent calls to resolve() must return the exact same instance."""
        nexus = JarvisNexus()
        instances = []
        barrier = threading.Barrier(8)

        class _UniqueSvc:
            pass

        call_count = {"n": 0}

        def _build(target_id, hint_path=None):
            call_count["n"] += 1
            return _UniqueSvc()

        def _worker():
            barrier.wait()  # All threads start at the same instant
            instances.append(nexus.resolve("shared_svc"))

        with patch.object(nexus, "_resolve_internal", side_effect=_build):
            threads = [threading.Thread(target=_worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        # All threads must have received an instance
        assert len(instances) == 8
        # All must be the same object (cached)
        first = instances[0]
        assert all(i is first for i in instances)


class TestAmbiguousDiscovery:
    """Tests for AmbiguousComponentError during filesystem discovery."""

    def test_ambiguous_discovery_raises_error(self):
        """_global_search_with_path must raise AmbiguousComponentError for >1 match."""
        nexus = JarvisNexus()

        class _FakeA:
            pass

        class _FakeB:
            pass

        # Simulate two candidates for the same component_id
        fake_candidates = [(_FakeA(), "app.mod_a.fake"), (_FakeB(), "app.mod_b.fake")]

        def _ambiguous(target_id):
            # Raise with two synthetic candidates
            if len(fake_candidates) > 1:
                paths = [p for _, p in fake_candidates]
                raise AmbiguousComponentError(target_id, paths)
            return fake_candidates[0] if fake_candidates else (None, None)

        with patch.object(nexus, "_global_search_with_path", side_effect=_ambiguous):
            result = nexus.resolve("fake")

        # AmbiguousComponentError is caught by _resolve_with_timeout → CloudMock returned
        assert isinstance(result, CloudMock)
        assert "fake" in nexus._circuit_breaker

    def test_ambiguous_component_error_carries_candidates(self):
        """AmbiguousComponentError should expose component_id and candidates."""
        err = AmbiguousComponentError("my_svc", ["app.a.my_svc", "app.b.my_svc"])
        assert err.component_id == "my_svc"
        assert "app.a.my_svc" in err.candidates
        assert "app.b.my_svc" in err.candidates


class TestCloudMockObservability:
    """Tests for CloudMock call tracking and metrics integration."""

    def test_cloudmock_records_calls_and_metrics(self):
        """CloudMock must track calls and forward to a metrics collector."""
        mock = CloudMock("obs_svc")

        collector = MagicMock()
        mock._metrics_collector = collector

        # Call an arbitrary method three times
        mock.do_something("a", key="b")
        mock.do_something("c")
        mock.another_method()

        assert mock._call_count == 3
        assert len(mock._last_calls) == 3
        assert mock._last_calls[0]["method"] == "do_something"
        assert mock._last_calls[2]["method"] == "another_method"

        # Metrics collector must have been notified for each call
        assert collector.increment.call_count == 3
        collector.increment.assert_called_with("nexus.fallback_count")

    def test_cloudmock_last_calls_capped_at_ten(self):
        """_last_calls must not grow beyond 10 entries."""
        mock = CloudMock("capped_svc")
        for i in range(20):
            mock.method_x(i)
        assert len(mock._last_calls) == 10

    def test_cloudmock_has_is_cloud_mock_flag(self):
        """CloudMock must advertise itself via __is_cloud_mock__."""
        assert CloudMock.__is_cloud_mock__ is True
        assert CloudMock("x").__is_cloud_mock__ is True


class TestNexusRegistryPath:
    """Tests that the Nexus registry is loaded from data/nexus_registry.json."""

    def test_registry_loaded_from_data_directory(self, tmp_path):
        """JarvisNexus should load registry from data/nexus_registry.json, not the project root."""
        import json
        import os

        # Create a temp project structure with data/nexus_registry.json
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        registry = {
            "components": {
                "test_service": "app.services.test_service.TestService"
            }
        }
        (data_dir / "nexus_registry.json").write_text(json.dumps(registry))

        nexus = JarvisNexus()
        nexus.base_dir = str(tmp_path)

        result = nexus._load_local_registry()

        assert "test_service" in result
        assert result["test_service"] == "app.services.test_service"

    def test_registry_not_found_at_root_returns_empty(self, tmp_path):
        """If registry is at root (wrong path), _load_local_registry should return {}."""
        import json

        # Put the registry at root level (wrong path)
        (tmp_path / "nexus_registry.json").write_text(
            json.dumps({"components": {"some_service": "app.some.SomeService"}})
        )

        nexus = JarvisNexus()
        nexus.base_dir = str(tmp_path)

        result = nexus._load_local_registry()
        # Should return empty because it looks in data/ not root
        assert result == {}

    def test_init_loads_registry_into_cache(self, tmp_path):
        """JarvisNexus.__init__ should pre-populate _cache from the registry."""
        import json
        import os

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        registry = {
            "components": {
                "telegram_adapter": "app.adapters.infrastructure.telegram_adapter.TelegramAdapter"
            }
        }
        (data_dir / "nexus_registry.json").write_text(json.dumps(registry))

        # Patch os.getcwd to point to tmp_path
        with patch("app.core.nexus.os.path.abspath") as mock_abs:
            mock_abs.return_value = str(tmp_path)
            nexus = JarvisNexus()

        assert "telegram_adapter" in nexus._cache
        assert nexus._cache["telegram_adapter"] == "app.adapters.infrastructure.telegram_adapter"
