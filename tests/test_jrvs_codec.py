# -*- coding: utf-8 -*-
"""Tests para o codec binário .jrvs (app/utils/jrvs_codec.py)."""

import pytest

from app.utils.jrvs_codec import JrvsDecodeError, decode, encode, read_file, write_file


class TestJrvsEncodeDecode:
    """Testes de roundtrip encode/decode."""

    def test_encode_returns_bytes(self):
        data = {"key": "value", "num": 42}
        raw = encode(data)
        assert isinstance(raw, bytes)

    def test_roundtrip_dict(self):
        data = {"nome": "JARVIS", "ativo": True, "versao": 1}
        assert decode(encode(data)) == data

    def test_roundtrip_list(self):
        data = [1, "dois", {"tres": 3}, None]
        assert decode(encode(data)) == data

    def test_roundtrip_nested(self):
        data = {"a": {"b": {"c": [1, 2, 3]}}}
        assert decode(encode(data)) == data

    def test_roundtrip_unicode(self):
        data = {"texto": "olá, mundo! 🤖"}
        assert decode(encode(data)) == data

    def test_roundtrip_no_compression(self):
        data = {"comprimido": False}
        raw = encode(data, compress=False)
        assert decode(raw) == data

    def test_roundtrip_with_compression(self):
        data = {"comprimido": True, "lista": list(range(100))}
        raw = encode(data, compress=True)
        assert decode(raw) == data

    def test_compressed_smaller_than_uncompressed_for_repetitive_data(self):
        data = {"texto": "x" * 1000}
        compressed = encode(data, compress=True)
        uncompressed = encode(data, compress=False)
        assert len(compressed) < len(uncompressed)

    def test_magic_header_present(self):
        raw = encode({"x": 1})
        assert raw[:4] == b"JRVS"


class TestJrvsDecodeErrors:
    """Testes de robustez — entradas inválidas."""

    def test_decode_empty_bytes_raises(self):
        with pytest.raises(JrvsDecodeError):
            decode(b"")

    def test_decode_wrong_magic_raises(self):
        raw = encode({"ok": True})
        corrupted = b"XXXX" + raw[4:]
        with pytest.raises(JrvsDecodeError, match="Magic inválido"):
            decode(corrupted)

    def test_decode_truncated_raises(self):
        raw = encode({"ok": True})
        with pytest.raises(JrvsDecodeError):
            decode(raw[:8])

    def test_decode_bad_crc_raises(self):
        raw = bytearray(encode({"ok": True}))
        # Corrompe o último byte dos dados
        raw[-1] ^= 0xFF
        with pytest.raises(JrvsDecodeError, match="CRC32 inválido"):
            decode(bytes(raw))


class TestJrvsFileIO:
    """Testes de leitura/gravação em arquivo."""

    def test_write_and_read_file(self, tmp_path):
        path = tmp_path / "test.jrvs"
        data = {"nexus": "registry", "version": 2}
        write_file(path, data)
        assert path.exists()
        assert read_file(path) == data

    def test_read_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_file(tmp_path / "nao_existe.jrvs")

    def test_write_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "subdir" / "deep" / "test.jrvs"
        write_file(path, [1, 2, 3])
        assert read_file(path) == [1, 2, 3]

    def test_large_data_roundtrip(self, tmp_path):
        path = tmp_path / "large.jrvs"
        data = {"items": [{"id": i, "nome": f"cap_{i:03d}"} for i in range(200)]}
        write_file(path, data)
        assert read_file(path) == data
