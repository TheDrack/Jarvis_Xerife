# -*- coding: utf-8 -*-
"""Tests for JarvisNexus - Circuit Breaker and CloudMock validation"""

import time
from unittest.mock import patch

import pytest

from app.core.nexus import CloudMock, JarvisNexus, _CIRCUIT_BREAKER_RESET


class TestCloudMock:
    """Tests for the CloudMock fallback component."""

    def test_execute_returns_failure_dict(self):
        mock = CloudMock("test_component")
        result = mock.execute()
        assert result["success"] is False
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
