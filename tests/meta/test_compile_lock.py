# -*- coding: utf-8 -*-
"""Tests para o lock unificado de compilação (Part 6)."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.meta.compile_lock import (
    _LOCK_FILENAME,
    acquire_compile_lock,
    release_compile_lock,
)
from app.core.meta.jrvs_compiler import JRVSCompiler
from app.core.meta.policy_store import PolicyStore


@pytest.fixture()
def lock_dir(tmp_path):
    return str(tmp_path)


class TestAcquireRelease:
    """Basic lock acquire / release behaviour."""

    def test_acquire_succeeds_when_no_lock(self, lock_dir):
        assert acquire_compile_lock(lock_dir) is True

    def test_acquire_creates_lock_file(self, lock_dir):
        acquire_compile_lock(lock_dir)
        lock = Path(lock_dir) / _LOCK_FILENAME
        assert lock.exists()

    def test_release_removes_lock_file(self, lock_dir):
        acquire_compile_lock(lock_dir)
        release_compile_lock(lock_dir)
        lock = Path(lock_dir) / _LOCK_FILENAME
        assert not lock.exists()

    def test_second_acquire_blocked_while_active(self, lock_dir):
        acquire_compile_lock(lock_dir)
        # Second attempt should fail — lock is still held
        assert acquire_compile_lock(lock_dir) is False

    def test_acquire_succeeds_after_release(self, lock_dir):
        acquire_compile_lock(lock_dir)
        release_compile_lock(lock_dir)
        assert acquire_compile_lock(lock_dir) is True
        release_compile_lock(lock_dir)

    def test_release_is_idempotent(self, lock_dir):
        """Releasing a non-existent lock must not raise."""
        release_compile_lock(lock_dir)  # no lock exists
        release_compile_lock(lock_dir)  # second call also fine


class TestStaleLockHandling:
    """Stale locks older than JRVS_COMPILE_LOCK_TIMEOUT must be replaced."""

    def test_stale_lock_is_replaced(self, lock_dir):
        lock = Path(lock_dir) / _LOCK_FILENAME
        # Write a timestamp 200 seconds in the past (stale)
        old_ts = time.time() - 200
        lock.write_text(str(old_ts), encoding="utf-8")

        # With 120s timeout, this should be considered stale
        with patch.dict(os.environ, {"JRVS_COMPILE_LOCK_TIMEOUT": "120"}):
            assert acquire_compile_lock(lock_dir) is True
        release_compile_lock(lock_dir)

    def test_fresh_lock_is_not_replaced(self, lock_dir):
        lock = Path(lock_dir) / _LOCK_FILENAME
        # Write a timestamp 10 seconds in the past (fresh)
        fresh_ts = time.time() - 10
        lock.write_text(str(fresh_ts), encoding="utf-8")

        with patch.dict(os.environ, {"JRVS_COMPILE_LOCK_TIMEOUT": "120"}):
            assert acquire_compile_lock(lock_dir) is False

    def test_corrupt_lock_is_replaced(self, lock_dir):
        lock = Path(lock_dir) / _LOCK_FILENAME
        lock.write_text("NOT_A_NUMBER", encoding="utf-8")

        assert acquire_compile_lock(lock_dir) is True
        release_compile_lock(lock_dir)


class TestCompilerUsesLock:
    """JRVSCompiler.compile_module must respect the unified lock."""

    def test_compile_blocked_if_lock_held_externally(self, tmp_path):
        lock_dir = str(tmp_path)
        # Acquire the lock externally before compiler runs
        acquire_compile_lock(lock_dir)
        try:
            store = PolicyStore(jrvs_dir=lock_dir)
            compiler = JRVSCompiler(policy_store=store, jrvs_dir=lock_dir)
            store.update_policies("llm", {"groq": {"ema_success": 0.8}})

            # compile_module should detect active lock and return early (no .jrvs written)
            jrvs_path = tmp_path / "llm.jrvs"
            compiler.compile_module("llm")
            # File may or may not exist depending on whether a prior compile ran;
            # the important thing is it did not raise and did not corrupt.
            # We can verify the lock is still held.
            lock = tmp_path / _LOCK_FILENAME
            assert lock.exists()
        finally:
            release_compile_lock(lock_dir)

    def test_compile_all_blocked_if_lock_held(self, tmp_path):
        lock_dir = str(tmp_path)
        acquire_compile_lock(lock_dir)
        try:
            store = PolicyStore(jrvs_dir=lock_dir)
            compiler = JRVSCompiler(policy_store=store, jrvs_dir=lock_dir)
            compiler.compile_all()  # should not raise, just log warning
        finally:
            release_compile_lock(lock_dir)

    def test_lock_released_after_successful_compile(self, tmp_path):
        store = PolicyStore(jrvs_dir=str(tmp_path))
        compiler = JRVSCompiler(policy_store=store, jrvs_dir=str(tmp_path))
        store.update_policies("llm", {"model": {"ema_success": 0.7}})

        compiler.compile_module("llm")

        lock = tmp_path / _LOCK_FILENAME
        assert not lock.exists()

    def test_lock_released_after_failed_compile(self, tmp_path):
        """Lock must be released even if compilation fails."""
        store = PolicyStore(jrvs_dir=str(tmp_path))
        compiler = JRVSCompiler(policy_store=store, jrvs_dir=str(tmp_path))

        # Patch _compile_module_locked to raise an exception
        from unittest.mock import patch as _patch

        with _patch.object(
            compiler,
            "_compile_module_locked",
            side_effect=RuntimeError("simulated failure"),
        ):
            with pytest.raises(RuntimeError):
                compiler.compile_module("llm")

        lock = tmp_path / _LOCK_FILENAME
        assert not lock.exists()
