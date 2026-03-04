# -*- coding: utf-8 -*-
"""Tests para JRVSCompiler (app/core/meta/jrvs_compiler.py)."""

import json
from pathlib import Path

import pytest

from app.core.meta.jrvs_compiler import JRVSCompiler
from app.core.meta.policy_store import PolicyStore


@pytest.fixture()
def tmp_store(tmp_path):
    """PolicyStore em diretório temporário."""
    return PolicyStore(jrvs_dir=str(tmp_path))


@pytest.fixture()
def compiler(tmp_path, tmp_store):
    """JRVSCompiler com PolicyStore em diretório temporário."""
    return JRVSCompiler(policy_store=tmp_store, jrvs_dir=str(tmp_path))


class TestCompileModule:
    """Testa criação de arquivos .jrvs e .json."""

    def test_compile_creates_jrvs_file(self, compiler, tmp_path):
        compiler._store.update_policies("llm", {"groq": {"ema_success": 0.9}})
        jrvs_path = compiler.compile_module("llm")
        assert jrvs_path.exists()
        assert jrvs_path.suffix == ".jrvs"

    def test_compile_creates_json_file(self, compiler, tmp_path):
        compiler._store.update_policies("llm", {"groq": {"ema_success": 0.9}})
        compiler.compile_module("llm")
        json_path = tmp_path / "llm.json"
        assert json_path.exists()

    def test_compile_returns_path(self, compiler, tmp_path):
        result = compiler.compile_module("tools")
        assert isinstance(result, Path)

    def test_compiled_json_contains_meta(self, compiler, tmp_path):
        compiler._store.update_policies("meta", {"epsilon": 0.1})
        compiler.compile_module("meta")
        json_path = tmp_path / "meta.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "meta" in data
        assert "compiled_at" in data["meta"]
        assert "compiler_version" in data["meta"]
        assert "sha256" in data["meta"]

    def test_compile_empty_module(self, compiler, tmp_path):
        """Módulo sem políticas ainda deve compilar com sucesso."""
        jrvs_path = compiler.compile_module("empty_module")
        assert jrvs_path.exists()


class TestValidateJrvs:
    """Testa validação CRC32 e SHA-256."""

    def test_validate_valid_file(self, compiler, tmp_path):
        compiler._store.update_policies("llm", {"groq": {"ema_success": 0.8}})
        jrvs_path = compiler.compile_module("llm")
        assert compiler.validate_jrvs(jrvs_path) is True

    def test_validate_corrupted_file(self, compiler, tmp_path):
        jrvs_path = compiler.compile_module("llm")
        # Corrupt last byte
        raw = bytearray(jrvs_path.read_bytes())
        raw[-1] ^= 0xFF
        jrvs_path.write_bytes(bytes(raw))
        assert compiler.validate_jrvs(jrvs_path) is False

    def test_validate_missing_file(self, compiler, tmp_path):
        assert compiler.validate_jrvs(tmp_path / "nonexistent.jrvs") is False

    def test_validate_tampered_sha256(self, compiler, tmp_path):
        """Altera o campo sha256 no JSON e reempacota: deve falhar na validação."""
        from app.utils import jrvs_codec

        compiler._store.update_policies("llm", {"groq": {"ema_success": 0.7}})
        jrvs_path = compiler.compile_module("llm")
        data = jrvs_codec.read_file(jrvs_path)
        data["meta"]["sha256"] = "aabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccddaabbccdd"
        jrvs_path.write_bytes(jrvs_codec.encode(data))
        assert compiler.validate_jrvs(jrvs_path) is False


class TestReadModule:
    """Testa leitura de módulos .jrvs."""

    def test_read_module_returns_dict(self, compiler, tmp_path):
        policies = {"gemini": {"ema_success": 0.75, "uses": 10}}
        compiler._store.update_policies("llm", policies)
        compiler.compile_module("llm")
        data = compiler.read_module("llm")
        assert isinstance(data, dict)
        assert data["module"] == "llm"
        assert data["policies"] == policies

    def test_read_module_missing_raises(self, compiler, tmp_path):
        with pytest.raises(FileNotFoundError):
            compiler.read_module("nonexistent_module")

    def test_read_module_matches_json(self, compiler, tmp_path):
        """Conteúdo do .jrvs deve coincidir com o .json de inspeção."""
        policies = {"tool_a": {"confidence": 0.9, "success_rate": 0.85}}
        compiler._store.update_policies("tools", policies)
        compiler.compile_module("tools")

        jrvs_data = compiler.read_module("tools")
        json_path = tmp_path / "tools.json"
        json_data = json.loads(json_path.read_text(encoding="utf-8"))

        # policies content must match
        assert jrvs_data["policies"] == json_data["policies"]
        assert jrvs_data["meta"]["sha256"] == json_data["meta"]["sha256"]


class TestShouldRecompile:
    """Testa heurística de recompilação."""

    def test_should_recompile_at_threshold(self, compiler):
        assert compiler.should_recompile("llm", 20) is True

    def test_should_not_recompile_below_threshold(self, compiler):
        assert compiler.should_recompile("llm", 19) is False

    def test_should_recompile_above_threshold(self, compiler):
        assert compiler.should_recompile("llm", 100) is True
