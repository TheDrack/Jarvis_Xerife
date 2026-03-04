# -*- coding: utf-8 -*-
"""Tests para o JrvsTranslator (app/application/services/jrvs_translator.py)."""

import json
import pytest

from app.application.services.jrvs_translator import JrvsTranslator
from app.utils.jrvs_codec import read_file as jrvs_read


@pytest.fixture
def translator():
    return JrvsTranslator()


class TestJrvsTranslatorConvertToJrvs:
    """Conversão de arquivos legíveis para .jrvs."""

    def test_convert_json_to_jrvs(self, translator, tmp_path):
        src = tmp_path / "registry.json"
        data = {"componente": "nexus", "ativo": True}
        src.write_text(json.dumps(data), encoding="utf-8")

        dest = translator.convert_to_jrvs(src)

        assert dest == src.with_suffix(".jrvs")
        assert dest.exists()
        assert jrvs_read(dest) == data

    def test_convert_txt_to_jrvs(self, translator, tmp_path):
        src = tmp_path / "notes.txt"
        src.write_text("anotação de teste", encoding="utf-8")

        dest = translator.convert_to_jrvs(src)

        assert dest.exists()
        from app.utils.jrvs_codec import read_file
        assert read_file(dest) == "anotação de teste"


class TestJrvsTranslatorConvertFromJrvs:
    """Conversão de .jrvs para arquivos legíveis."""

    def test_convert_jrvs_to_json(self, translator, tmp_path):
        from app.utils.jrvs_codec import write_file
        src = tmp_path / "data.jrvs"
        data = {"nexus": True, "items": [1, 2, 3]}
        write_file(src, data)

        dest = translator.convert_from_jrvs(src, ".json")

        assert dest == src.with_suffix(".json")
        assert json.loads(dest.read_text(encoding="utf-8")) == data

    def test_convert_jrvs_default_target_is_json(self, translator, tmp_path):
        from app.utils.jrvs_codec import write_file
        src = tmp_path / "file.jrvs"
        write_file(src, {"k": "v"})

        dest = translator.convert_from_jrvs(src)
        assert dest.suffix == ".json"


class TestJrvsTranslatorExecute:
    """Interface NexusComponent — método execute()."""

    def test_execute_sync_all(self, translator, tmp_path):
        # Prepara um JSON no diretório temporário
        (tmp_path / "config.json").write_text('{"ok": true}', encoding="utf-8")

        result = translator.execute({"action": "sync_all", "data_dir": str(tmp_path)})

        assert result["success"] is True
        assert len(result["translated"]) >= 1
        assert (tmp_path / "config.jrvs").exists()

    def test_execute_to_jrvs(self, translator, tmp_path):
        (tmp_path / "file.json").write_text('{"a": 1}', encoding="utf-8")

        result = translator.execute({"action": "to_jrvs", "data_dir": str(tmp_path)})

        assert (tmp_path / "file.jrvs").exists()
        assert result["action"] == "to_jrvs"

    def test_execute_from_jrvs(self, translator, tmp_path):
        from app.utils.jrvs_codec import write_file
        write_file(tmp_path / "snap.jrvs", {"snap": 1})

        result = translator.execute({"action": "from_jrvs", "data_dir": str(tmp_path)})

        assert (tmp_path / "snap.json").exists()

    def test_execute_specific_path(self, translator, tmp_path):
        src = tmp_path / "specific.json"
        src.write_text('{"path": "specific"}', encoding="utf-8")

        result = translator.execute({"action": "to_jrvs", "path": str(src)})

        assert (tmp_path / "specific.jrvs").exists()
        assert result["success"] is True

    def test_execute_empty_context_uses_defaults(self, translator, tmp_path):
        """execute() sem contexto não deve lançar exceção."""
        translator._data_dir = tmp_path
        result = translator.execute(None)
        assert "success" in result

    def test_execute_nonexistent_dir_returns_success(self, translator):
        result = translator.execute({"action": "to_jrvs", "data_dir": "/tmp/dir_inexistente_xyz"})
        assert "success" in result
