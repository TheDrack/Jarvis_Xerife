# -*- coding: utf-8 -*-
"""Contrato de documentação: os docs não podem citar arquivos inexistentes.

README, guia do agente e README de scripts já apontaram para arquivos removidos
(`scripts/evolution_mutator.py`, `pipeline_builder.py`,
`ci-failure-to-issue.yml`, …), o que faz a documentação perder credibilidade.
Este teste varre os documentos, extrai as referências a arquivos por extensão e
exige que cada uma resolva para um arquivo real do repositório.

Uma referência pode ser aceita sem arquivo correspondente apenas se estiver em
``_ALLOWED_MISSING`` **com um motivo** — artefato gerado em runtime ou nome usado
em exemplo de log/CLI, por exemplo. Nunca adicione uma entrada para silenciar um
link quebrado de verdade: corrija a documentação.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Documentos vivos: mudam com o código e são verificados aqui.
# `docs/ARQUIVO_MAP.md` fica fora: é gerado pelo `scripts/autodoc.py` a partir do
# codebase, então não é uma afirmação escrita à mão.
CHECKED_DOCS: Tuple[str, ...] = (
    "README.md",
    "docs/AGENT_GUIDE.md",
    "docs/STATUS.md",
    "docs/NEXUS.md",
    "docs/PIPELINE_RUNNER.md",
    "scripts/README.md",
)

# Diretórios irrelevantes (dependências, caches, VCS).
_SKIP_DIRS: Set[str] = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "htmlcov",
    "node_modules",
}

_EXT = r"(?:py|yml|yaml|json|jrvs|txt|md|sh|cfg|ini|toml)"

# Candidatos a referência de arquivo, ex.: `scripts/pr_manager.py`, `homeostase.yml`.
# O lookbehind evita capturar fragmentos de URL (github.com/.../homeostase.yml).
_FILE_REF_RE = re.compile(rf"(?<![\w./\-])([A-Za-z0-9_][A-Za-z0-9_./\-]*\.{_EXT})\b")
# Caminhos iniciados por ponto (`./scripts/x.py`, `.github/workflows/ci.yml`): o
# ponto faz parte do token, e o lookbehind garante que ele não venha de dentro de
# uma URL (em `github.com`, o ponto é precedido por caractere de palavra).
_DOTTED_FILE_REF_RE = re.compile(rf"(?<![\w./\-])(\.[A-Za-z0-9_./\-]*[A-Za-z0-9_]\.{_EXT})\b")

_FILE_REF_RES = (_FILE_REF_RE, _DOTTED_FILE_REF_RE)

# Referências aceitas sem arquivo correspondente (cada uma com motivo).
# A lista é auditada: `test_allowlist_has_no_stale_entries` remove a necessidade de
# manter exceções que voltaram a existir ou que nenhum doc usa mais.
_ALLOWED_MISSING: Dict[str, str] = {
    # Artefatos gerados em runtime (não versionados).
    "CORE_LOGIC_CONSOLIDATED.txt": "gerado pelo pipeline `sync_drive` (consolidator)",
    "data/nexus_registry.jrvs": "espelho .jrvs criado sob demanda pelo document_store",
    # Nomes citados em exemplos de log/CLI, não arquivos do repositório.
    "app/main.py": "exemplo de traceback na seção de padrões de erro",
    "app/utils.py": "exemplo de mensagem de erro na seção de padrões de erro",
    "report.json": "artefato de runtime citado nos exemplos de CLI",
    "pytest_log.txt": "artefato de runtime citado nos exemplos de CLI",
    "failed_workflow_logs.txt": "artefato de runtime citado nos exemplos de CLI",
    # Documentados explicitamente como removidos/migrados (histórico).
    "scripts/evolution_mutator.py": "removido do repositório; documentado como tal",
}


def _repo_paths() -> List[Path]:
    """Todos os arquivos versionáveis do repositório (sem caches/dependências)."""
    paths: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            paths.append(Path(dirpath, name))
    return paths


def _normalize(token: str) -> str:
    """Remove o prefixo ``./`` sem tocar em caminhos ocultos (``.github/...``)."""
    return token[2:] if token.startswith("./") else token


def _references(text: str) -> Iterator[Tuple[str, int]]:
    """Itera sobre (referência, linha) encontradas em *text*."""
    seen: Set[Tuple[str, int]] = set()
    for pattern in _FILE_REF_RES:
        for match in pattern.finditer(text):
            token = _normalize(match.group(1))
            # Placeholders (`config/pipelines/<nome>.yml`), globs e reticências
            # não são referências a arquivos concretos.
            if any(ch in token for ch in "<>*{}"):
                continue
            if token.endswith(".") or token.startswith(("http://", "https://")):
                continue
            position = (token, text.count("\n", 0, match.start()) + 1)
            if position in seen:
                continue
            seen.add(position)
            yield position


def _resolve(
    token: str,
    suffixes: Set[str],
    basenames: Set[str],
    doc_dir: Path = REPO_ROOT,
) -> bool:
    """True quando *token* aponta para um arquivo real do repositório.

    Tenta, em ordem: caminho relativo ao documento (links `../x`), caminho
    relativo ao root e sufixo de diretórios/nome usado de forma abreviada nos
    docs (ex.: `services/assistant_service.py`).
    """
    normalized = _normalize(token)
    if "../" in normalized:
        try:
            candidate = (doc_dir / normalized).resolve()
        except (OSError, ValueError):
            return False
        inside_repo = candidate == REPO_ROOT or REPO_ROOT in candidate.parents
        return candidate.exists() and inside_repo

    if "/" in normalized:
        if (REPO_ROOT / normalized).exists():
            return True
        return any(
            suffix == normalized or suffix.endswith("/" + normalized) for suffix in suffixes
        )
    return normalized in basenames


def _suffixes_and_basenames(paths: List[Path]) -> Tuple[Set[str], Set[str]]:
    suffixes: Set[str] = set()
    basenames: Set[str] = set()
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        basenames.add(path.name)
        parts = rel.split("/")
        for index in range(len(parts)):
            suffixes.add("/".join(parts[index:]))
    return suffixes, basenames


class TestReferenceExtraction:
    """A extração precisa ver arquivos reais sem confundir URL/placeholder."""

    def test_extracts_workflow_and_hidden_paths(self):
        text = "Rode `.github/workflows/homeostase.yml` e `scripts/pr_manager.py`."
        tokens = {token for token, _ in _references(text)}
        assert tokens == {".github/workflows/homeostase.yml", "scripts/pr_manager.py"}

    def test_ignores_badge_urls(self):
        """Fragmento de URL não é referência a arquivo local."""
        text = "[![badge](https://github.com/o/r/actions/workflows/homeostase.yml/badge.svg)](x)"
        assert list(_references(text)) == []

    def test_ignores_placeholders_and_normalizes_relative_paths(self):
        text = "Rodar `config/pipelines/<nome>.yml` com `./scripts/autodoc.py`"
        tokens = {token for token, _ in _references(text)}
        assert tokens == {"scripts/autodoc.py"}, "placeholder não é referência concreta"

    def test_reports_line_numbers(self):
        text = " linha 1\n linha 2 com `docs/PIPELINE_RUNNER.md`\n"
        assert list(_references(text)) == [("docs/PIPELINE_RUNNER.md", 2)]


def test_checked_docs_exist():
    """Os documentos cobertos pelo contrato precisam existir."""
    missing = [doc for doc in CHECKED_DOCS if not (REPO_ROOT / doc).exists()]
    assert not missing, f"Documentos monitorados não encontrados: {missing}"


def test_docs_do_not_reference_missing_files():
    """Nenhum doc pode citar arquivo/script/workflow que não existe."""
    paths = _repo_paths()
    suffixes, basenames = _suffixes_and_basenames(paths)

    unresolved: List[str] = []
    for doc in CHECKED_DOCS:
        doc_path = REPO_ROOT / doc
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")
        for token, line in _references(text):
            if token in _ALLOWED_MISSING:
                continue
            if _resolve(token, suffixes, basenames, doc_dir=doc_path.parent):
                continue
            unresolved.append(f"{doc}:{line} → {token}")

    assert not unresolved, (
        "Referências a arquivos inexistentes na documentação:\n  "
        + "\n  ".join(sorted(set(unresolved)))
        + "\n\nCorrija o caminho/link ou, se for artefato de runtime ou exemplo de "
        "log, registre-o em _ALLOWED_MISSING (com motivo)."
    )


def test_allowlist_entries_are_documented_exceptions():
    """Cada exceção registrada precisa ter um motivo não vazio."""
    undocumented = [token for token, reason in _ALLOWED_MISSING.items() if not reason.strip()]
    assert not undocumented, f"Exceções sem motivo em _ALLOWED_MISSING: {undocumented}"


def test_allowlist_has_no_stale_entries():
    """Cada exceção precisa ainda ser necessária e realmente usada nos docs."""
    paths = _repo_paths()
    suffixes, basenames = _suffixes_and_basenames(paths)

    now_existing = [token for token in _ALLOWED_MISSING if _resolve(token, suffixes, basenames)]

    referenced: Set[str] = set()
    for doc in CHECKED_DOCS:
        doc_path = REPO_ROOT / doc
        if doc_path.exists():
            referenced.update(token for token, _ in _references(doc_path.read_text(encoding="utf-8")))
    unused = [token for token in _ALLOWED_MISSING if token not in referenced]

    problems = []
    if now_existing:
        problems.append(
            "Já existem no repositório (remova a exceção): " + ", ".join(sorted(now_existing))
        )
    if unused:
        problems.append(
            "Nenhum doc monitorado usa mais (remova a exceção): " + ", ".join(sorted(unused))
        )
    assert not problems, "\n".join(problems)
