# -*- coding: utf-8 -*-
"""
Codec para o formato binário .jrvs do JARVIS.

O formato .jrvs é um contêiner binário leve para persistência interna do JARVIS.
Ele armazena dados estruturados (dicts/lists) como JSON comprimido com zlib,
precedido de um cabeçalho fixo com magic bytes, versão, flags e CRC32.

Layout do arquivo::

    ┌─────────────────────────────────────────────────┐
    │  Magic  │ Version │  Flags  │   CRC32   │  Len  │
    │  4 bytes│ 2 bytes │ 2 bytes │  4 bytes  │4 bytes│
    ├─────────────────────────────────────────────────┤
    │                     Data                        │
    │           (JSON bytes, zlib-compressed)         │
    └─────────────────────────────────────────────────┘

- Magic: b'JRVS'
- Version: uint16 little-endian (atual = 1)
- Flags: uint16 little-endian (bit 0 = comprimido)
- CRC32: uint32 little-endian do bloco de dados
- Len:   uint32 little-endian do bloco de dados
"""

import json
import struct
import zlib
from pathlib import Path
from typing import Any, Union

_MAGIC = b"JRVS"
_VERSION = 1
_FLAG_COMPRESSED = 0x0001
_HEADER_FMT = "<4sHHII"  # magic(4s), version(H), flags(H), crc32(I), length(I)
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)  # 16 bytes


class JrvsDecodeError(Exception):
    """Raised when a .jrvs file cannot be decoded."""


def encode(data: Any, compress: bool = True) -> bytes:
    """Serializa *data* no formato binário .jrvs.

    Args:
        data: Objeto serializável em JSON (dict, list, str, int, float, bool, None).
        compress: Se True (padrão) aplica compressão zlib ao payload.

    Returns:
        Bytes completos prontos para gravação em disco.
    """
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if compress:
        payload = zlib.compress(payload, level=zlib.Z_BEST_COMPRESSION)
    flags = _FLAG_COMPRESSED if compress else 0
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = struct.pack(_HEADER_FMT, _MAGIC, _VERSION, flags, crc, len(payload))
    return header + payload


def decode(raw: bytes) -> Any:
    """Desserializa bytes no formato .jrvs de volta para objeto Python.

    Args:
        raw: Bytes brutos lidos do arquivo .jrvs.

    Returns:
        Objeto Python original.

    Raises:
        JrvsDecodeError: Se o cabeçalho for inválido, versão desconhecida ou CRC falhar.
    """
    if len(raw) < _HEADER_SIZE:
        raise JrvsDecodeError(f"Arquivo muito pequeno: {len(raw)} bytes (mínimo {_HEADER_SIZE})")

    magic, version, flags, crc_stored, length = struct.unpack_from(_HEADER_FMT, raw)

    if magic != _MAGIC:
        raise JrvsDecodeError(f"Magic inválido: {magic!r} (esperado {_MAGIC!r})")
    if version != _VERSION:
        raise JrvsDecodeError(f"Versão desconhecida: {version} (suportado: {_VERSION})")

    payload = raw[_HEADER_SIZE : _HEADER_SIZE + length]
    if len(payload) != length:
        raise JrvsDecodeError(f"Dados truncados: esperado {length} bytes, obtido {len(payload)}")

    crc_actual = zlib.crc32(payload) & 0xFFFFFFFF
    if crc_actual != crc_stored:
        raise JrvsDecodeError(
            f"CRC32 inválido: esperado {crc_stored:#010x}, obtido {crc_actual:#010x}"
        )

    if flags & _FLAG_COMPRESSED:
        try:
            payload = zlib.decompress(payload)
        except zlib.error as exc:
            raise JrvsDecodeError(f"Erro ao descomprimir: {exc}") from exc

    return json.loads(payload.decode("utf-8"))


def write_file(path: Union[str, Path], data: Any, compress: bool = True) -> None:
    """Grava *data* em um arquivo .jrvs.

    Args:
        path: Caminho do arquivo de destino.
        data: Objeto Python serializável.
        compress: Se True (padrão) aplica compressão zlib.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode(data, compress=compress))


def read_file(path: Union[str, Path]) -> Any:
    """Lê e desserializa um arquivo .jrvs.

    Args:
        path: Caminho do arquivo .jrvs.

    Returns:
        Objeto Python original.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        JrvsDecodeError: Se o arquivo estiver corrompido ou em formato inválido.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo .jrvs não encontrado: {path}")
    return decode(path.read_bytes())
