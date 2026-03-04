# -*- coding: utf-8 -*-
"""Tests para gatilho de recompilação no PolicyStore."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.meta.policy_store import PolicyStore


@pytest.fixture()
def store_with_mock(tmp_path):
    """PolicyStore com threshold=5 e callback mockado."""
    callback = MagicMock()
    store = PolicyStore(jrvs_dir=str(tmp_path), recompile_threshold=5, on_threshold=callback)
    return store, callback


class TestRecompileTrigger:
    """Verifica que o PolicyStore dispara recompilação no threshold."""

    def test_callback_not_called_below_threshold(self, store_with_mock):
        store, callback = store_with_mock
        for i in range(4):
            store.update_policies("llm", {"k": i})
        callback.assert_not_called()

    def test_callback_called_at_threshold(self, store_with_mock):
        store, callback = store_with_mock
        for i in range(5):
            store.update_policies("llm", {"k": i})
        callback.assert_called_once_with("llm")

    def test_counter_resets_after_threshold(self, store_with_mock):
        store, callback = store_with_mock
        for i in range(5):
            store.update_policies("llm", {"k": i})
        assert store.get_update_counter("llm") == 0

    def test_callback_called_again_after_reset(self, store_with_mock):
        store, callback = store_with_mock
        for i in range(10):
            store.update_policies("llm", {"k": i})
        assert callback.call_count == 2

    def test_different_modules_independent_counters(self, store_with_mock):
        store, callback = store_with_mock
        for i in range(4):
            store.update_policies("llm", {"k": i})
            store.update_policies("tools", {"k": i})
        # neither module has reached threshold 5 yet
        callback.assert_not_called()
        store.update_policies("llm", {"k": 99})
        # llm reached threshold; tools didn't yet
        callback.assert_called_once_with("llm")

    def test_patch_policy_increments_counter(self, tmp_path):
        callback = MagicMock()
        store = PolicyStore(jrvs_dir=str(tmp_path), recompile_threshold=3, on_threshold=callback)
        store.patch_policy("meta", "epsilon", 0.1)
        store.patch_policy("meta", "epsilon", 0.05)
        callback.assert_not_called()
        store.patch_policy("meta", "epsilon", 0.01)
        callback.assert_called_once_with("meta")

    def test_compiler_integration_at_threshold(self, tmp_path):
        """JRVSCompiler.compile_module deve ser chamado quando threshold é atingido."""
        from app.core.meta.jrvs_compiler import JRVSCompiler

        compiler = JRVSCompiler(jrvs_dir=str(tmp_path))
        compile_calls = []

        def on_thresh(module_name: str) -> None:
            compile_calls.append(module_name)
            compiler.compile_module(module_name)

        store = PolicyStore(
            jrvs_dir=str(tmp_path), recompile_threshold=3, on_threshold=on_thresh
        )
        compiler._store = store

        for i in range(3):
            store.update_policies("tools", {"tool_x": {"confidence": i * 0.1}})

        assert "tools" in compile_calls
        jrvs_path = tmp_path / "tools.jrvs"
        assert jrvs_path.exists()
