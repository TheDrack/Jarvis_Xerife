# -*- coding: utf-8 -*-
"""Tests para validação de schema_version (Part 1 + Part 8 fallback)."""

import pytest

from app.core.meta.decision_engine import DecisionEngine
from app.core.meta.jrvs_compiler import JRVSCompiler, SchemaVersionError, _SCHEMA_VERSION
from app.core.meta.policy_store import PolicyStore
from app.utils import jrvs_codec


@pytest.fixture()
def store(tmp_path):
    return PolicyStore(jrvs_dir=str(tmp_path))


@pytest.fixture()
def compiler(tmp_path, store):
    return JRVSCompiler(policy_store=store, jrvs_dir=str(tmp_path))


class TestSchemaVersionInMeta:
    """Compiled .jrvs must include schema_version = 1.1 and decision_model_version."""

    def test_compiled_jrvs_has_schema_version(self, compiler, store):
        store.update_policies("llm", {"groq": {"ema_success": 0.8}})
        jrvs_path = compiler.compile_module("llm")
        data = jrvs_codec.read_file(jrvs_path)
        assert data["meta"]["schema_version"] == _SCHEMA_VERSION

    def test_compiled_jrvs_has_decision_model_version(self, compiler, store):
        store.update_policies("llm", {"groq": {"ema_success": 0.8}})
        jrvs_path = compiler.compile_module("llm")
        data = jrvs_codec.read_file(jrvs_path)
        assert "decision_model_version" in data["meta"]

    def test_compiled_jrvs_has_module_name(self, compiler, store):
        store.update_policies("tools", {"tool_a": {"confidence": 0.9}})
        jrvs_path = compiler.compile_module("tools")
        data = jrvs_codec.read_file(jrvs_path)
        assert data["meta"]["module_name"] == "tools"

    def test_json_sidecar_has_schema_version(self, compiler, store, tmp_path):
        import json

        store.update_policies("meta", {"epsilon": 0.1})
        compiler.compile_module("meta")
        json_path = tmp_path / "meta.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["meta"]["schema_version"] == _SCHEMA_VERSION


class TestSchemaVersionValidation:
    """read_module() must raise SchemaVersionError on schema mismatch."""

    def test_read_module_rejects_old_schema(self, compiler, store, tmp_path):
        # Write a .jrvs with schema_version "1.0" (old)
        old_payload = {
            "module": "llm",
            "policies": {"old_model": {"ema_success": 0.5}},
            "meta": {
                "schema_version": "1.0",
                "compiled_at": "2024-01-01T00:00:00+00:00",
                "module_name": "llm",
            },
        }
        jrvs_path = tmp_path / "llm.jrvs"
        jrvs_path.write_bytes(jrvs_codec.encode(old_payload))

        with pytest.raises(SchemaVersionError):
            compiler.read_module("llm")

    def test_read_module_rejects_missing_schema(self, compiler, store, tmp_path):
        payload = {
            "module": "llm",
            "policies": {},
            "meta": {"compiled_at": "2024-01-01T00:00:00+00:00"},
        }
        jrvs_path = tmp_path / "llm.jrvs"
        jrvs_path.write_bytes(jrvs_codec.encode(payload))

        with pytest.raises(SchemaVersionError):
            compiler.read_module("llm")

    def test_read_module_accepts_current_schema(self, compiler, store):
        store.update_policies("llm", {"groq": {"ema_success": 0.9}})
        compiler.compile_module("llm")
        data = compiler.read_module("llm")  # must not raise
        assert data["meta"]["schema_version"] == _SCHEMA_VERSION


class TestDecisionEngineFallbackOnSchemaMismatch:
    """DecisionEngine must fall back to PolicyStore on schema mismatch."""

    def test_fallback_on_schema_mismatch(self, tmp_path, store, compiler):
        # Write old schema jrvs
        old_payload = {
            "module": "llm",
            "policies": {"legacy_model": {"ema_success": 0.6}},
            "meta": {"schema_version": "0.9", "module_name": "llm"},
        }
        jrvs_path = tmp_path / "llm.jrvs"
        jrvs_path.write_bytes(jrvs_codec.encode(old_payload))

        # PolicyStore has current data
        store.update_policies("llm", {"current_model": {"ema_success": 0.75}})

        engine = DecisionEngine(compiler=compiler, policy_store=store)
        result = engine.decide({"command": "test"})

        # Should use fallback (PolicyStore), not the mismatched .jrvs
        assert result.chosen == "current_model"
        assert result.jrvs_version == "fallback"

    def test_fallback_on_corrupted_jrvs(self, tmp_path, store, compiler):
        # Write garbage bytes as a .jrvs
        jrvs_path = tmp_path / "llm.jrvs"
        jrvs_path.write_bytes(b"GARBAGE_BYTES_NOT_VALID_JRVS")

        store.update_policies("llm", {"good_model": {"ema_success": 0.8}})

        engine = DecisionEngine(compiler=compiler, policy_store=store)
        result = engine.decide({"command": "test"})
        assert result.chosen == "good_model"
        assert result.jrvs_version == "fallback"

    def test_fallback_on_missing_jrvs(self, tmp_path, store, compiler):
        # No .jrvs file at all, only PolicyStore data
        store.update_policies("llm", {"only_store_model": {"ema_success": 0.65}})

        engine = DecisionEngine(compiler=compiler, policy_store=store)
        result = engine.decide({})
        assert result.chosen == "only_store_model"
        assert result.jrvs_version == "fallback"
