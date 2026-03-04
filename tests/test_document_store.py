# -*- coding: utf-8 -*-
"""Tests para o DocumentStore universal (app/utils/document_store.py)."""

import json
import pytest

from app.utils.document_store import DocumentStore


@pytest.fixture
def store():
    return DocumentStore()


class TestDocumentStoreJson:
    """Leitura/escrita de arquivos .json."""

    def test_write_and_read_json(self, store, tmp_path):
        path = tmp_path / "test.json"
        data = {"componente": "nexus", "ativo": True}
        store.write(path, data)
        result = store.read(path)
        assert result == data

    def test_json_indented(self, store, tmp_path):
        path = tmp_path / "indented.json"
        data = {"a": 1}
        store.write(path, data, indent=4)
        raw = path.read_text(encoding="utf-8")
        assert "    " in raw  # indent=4 gera espaços

    def test_read_json_file_not_found(self, store, tmp_path):
        with pytest.raises(FileNotFoundError):
            store.read(tmp_path / "inexistente.json")

    def test_write_creates_parent_dirs(self, store, tmp_path):
        path = tmp_path / "sub" / "deep" / "file.json"
        store.write(path, {"x": 1})
        assert json.loads(path.read_text()) == {"x": 1}


class TestDocumentStoreJrvs:
    """Leitura/escrita de arquivos .jrvs via DocumentStore."""

    def test_write_and_read_jrvs(self, store, tmp_path):
        path = tmp_path / "test.jrvs"
        data = {"nexus": True, "version": 1}
        store.write(path, data)
        assert store.read(path) == data

    def test_jrvs_is_binary(self, store, tmp_path):
        path = tmp_path / "test.jrvs"
        store.write(path, {"bin": True})
        raw = path.read_bytes()
        assert raw[:4] == b"JRVS"


class TestDocumentStoreTxt:
    """Leitura/escrita de arquivos de texto puro."""

    def test_write_and_read_txt(self, store, tmp_path):
        path = tmp_path / "notes.txt"
        store.write(path, "conteúdo do arquivo")
        assert store.read(path) == "conteúdo do arquivo"

    def test_write_non_string_coerced(self, store, tmp_path):
        path = tmp_path / "data.txt"
        store.write(path, 42)
        assert store.read(path) == "42"


class TestDocumentStoreAutoDetect:
    """Detecção automática de formato por extensão."""

    def test_json_extension_uses_json(self, store, tmp_path):
        path = tmp_path / "file.json"
        store.write(path, [1, 2, 3])
        result = store.read(path)
        assert result == [1, 2, 3]

    def test_jrvs_extension_uses_jrvs(self, store, tmp_path):
        path = tmp_path / "file.jrvs"
        store.write(path, {"x": 99})
        result = store.read(path)
        assert result == {"x": 99}

    def test_unknown_extension_falls_back_to_text(self, store, tmp_path):
        path = tmp_path / "file.dat"
        store.write(path, "dados brutos")
        assert store.read(path) == "dados brutos"
