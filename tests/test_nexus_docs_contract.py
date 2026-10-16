# -*- coding: utf-8 -*-
"""Contrato dos docs do Nexus: a tabela de configuração deve espelhar o código.

`docs/NEXUS.md` documenta os timeouts do circuit breaker e da descoberta. Se os
defaults do código (`app/core/nexus_exceptions.py`) mudarem sem atualizar a tabela
(ou vice-versa), este teste falha — foi assim que a tabela ficou com valores
errados (`NEXUS_INSTANTIATE_TIMEOUT` 30s em vez de 5s, reset 300s em vez de 60s,
`NEXUS_IMPORT_TIMEOUT` ausente).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core import nexus_exceptions as nx_exc

REPO_ROOT = Path(__file__).resolve().parent.parent
NEXUS_DOC = REPO_ROOT / "docs" / "NEXUS.md"

# variável de ambiente documentada -> (valor no código, atributo do módulo)
_DOCUMENTED_DEFAULTS = {
    "NEXUS_TIMEOUT": ("CIRCUIT_BREAKER_TIMEOUT", 30.0),
    "NEXUS_CIRCUIT_RESET": ("CIRCUIT_BREAKER_RESET", 60.0),
    "NEXUS_IMPORT_TIMEOUT": ("NEXUS_IMPORT_TIMEOUT", 10.0),
    "NEXUS_INSTANTIATE_TIMEOUT": ("NEXUS_INSTANTIATE_TIMEOUT", 5.0),
}


def _documented_seconds() -> dict:
    """Extrai {variável: segundos} da tabela de configuração do NEXUS.md."""
    text = NEXUS_DOC.read_text(encoding="utf-8")
    found = {}
    for var, (_attribute, _default) in _DOCUMENTED_DEFAULTS.items():
        match = re.search(rf"`{var}`\s*\|\s*([0-9.]+)s", text)
        if match:
            found[var] = float(match.group(1))
    return found


def test_nexus_doc_exists():
    assert NEXUS_DOC.exists(), "docs/NEXUS.md precisa existir para o contrato valer"


def test_documented_env_vars_are_all_present():
    """Toda variável da tabela precisa estar documentada em NEXUS.md."""
    documented = _documented_seconds()
    missing = sorted(set(_DOCUMENTED_DEFAULTS) - set(documented))
    assert not missing, f"Variáveis não documentadas em docs/NEXUS.md: {missing}"


@pytest.mark.parametrize("env_var", sorted(_DOCUMENTED_DEFAULTS))
def test_documented_default_matches_code(env_var):
    """O default documentado deve ser igual ao default no código."""
    attribute, expected_in_code = _DOCUMENTED_DEFAULTS[env_var]
    code_value = float(getattr(nx_exc, attribute))

    assert code_value == expected_in_code, (
        f"Default de {env_var} mudou no código ({code_value}s); atualize "
        f"_DOCUMENTED_DEFAULTS e docs/NEXUS.md"
    )
    documented_value = _documented_seconds()[env_var]
    assert documented_value == code_value, (
        f"{env_var}: docs/NEXUS.md diz {documented_value}s, código diz {code_value}s"
    )


def test_strict_mode_documented_as_false():
    """`NEXUS_STRICT_MODE` é documentado como false (default do código)."""
    text = NEXUS_DOC.read_text(encoding="utf-8")
    assert re.search(r"`NEXUS_STRICT_MODE`\s*\|\s*false", text), (
        "docs/NEXUS.md deve documentar NEXUS_STRICT_MODE com default false"
    )
    assert nx_exc.NEXUS_STRICT_MODE is False, (
        "O default de NEXUS_STRICT_MODE no código deve ser false"
    )
