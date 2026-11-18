#!/usr/bin/env python3
"""Read-only hourly curiosity audit: roadmap, unfinished markers, and test outcome."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "STATUS.md"
ROADMAP = ROOT / "docs" / "COGNITIVE_ROADMAP.md"
REPORT_DIR = ROOT / "audit-output"
REPORT = REPORT_DIR / "hourly-curiosity-report.md"
TEST_LOG = REPORT_DIR / "pytest.log"
_STATUS_START = "<!-- JARVIS_COGNITIVE_EVIDENCE_START -->"
_STATUS_END = "<!-- JARVIS_COGNITIVE_EVIDENCE_END -->"
_COMMIT_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/commit/[0-9a-f]{40}$")
_ACTIONS_RUN_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/actions/runs/[0-9]+$")


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.splitlines() if result.returncode == 0 else []


def _valid_completion_evidence(evidence: object) -> bool:
    """Require the same minimum immutable evidence shape as the roadmap ledger."""
    if not isinstance(evidence, dict):
        return False
    commit_url = evidence.get("commit_url")
    check_urls = evidence.get("check_urls")
    if not isinstance(commit_url, str) or not _COMMIT_URL_RE.fullmatch(commit_url):
        return False
    if (
        not isinstance(check_urls, list)
        or not check_urls
        or any(
            not isinstance(url, str) or not _ACTIONS_RUN_URL_RE.fullmatch(url)
            for url in check_urls
        )
    ):
        return False

    for field in ("implementation_paths", "consumer_paths", "test_paths"):
        values = evidence.get(field)
        if not isinstance(values, list) or not values:
            return False
        for relative_path in values:
            if (
                not isinstance(relative_path, str)
                or not relative_path
                or relative_path != relative_path.strip()
                or relative_path.startswith(("/", "\\\\"))
                or "\\\\" in relative_path
                or ".." in relative_path.split("/")
            ):
                return False
            if field == "test_paths" and (
                not relative_path.startswith("tests/")
                or not relative_path.endswith(".py")
            ):
                return False
    return True


def _status_criterion_states(status_text: str) -> dict[str, str]:
    """Read criterion states from the machine-readable STATUS evidence ledger.

    A missing, malformed, or duplicated ledger is treated as unknown. A record
    marked verified without the required commit/check/path evidence is not
    trusted as complete.
    """
    if status_text.count(_STATUS_START) != 1 or status_text.count(_STATUS_END) != 1:
        return {}
    start = status_text.index(_STATUS_START) + len(_STATUS_START)
    end = status_text.index(_STATUS_END)
    if end <= start:
        return {}
    block = status_text[start:end]
    match = re.fullmatch(r"\s*```json\s*(\{.*\})\s*```\s*", block, re.DOTALL)
    if match is None:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("roadmap_path") != "docs/COGNITIVE_ROADMAP.md"
        or not isinstance(payload.get("criteria"), list)
    ):
        return {}

    states: dict[str, str] = {}
    for entry in payload["criteria"]:
        if not isinstance(entry, dict):
            return {}
        criterion_id = entry.get("criterion_id")
        state = entry.get("state")
        if (
            not isinstance(criterion_id, str)
            or not re.fullmatch(r"C[0-8]-[A-Z0-9]+(?:-[A-Z0-9]+)*", criterion_id)
            or state not in {"pending", "blocked", "verified"}
            or criterion_id in states
        ):
            return {}
        if state == "verified" and not _valid_completion_evidence(entry.get("evidence")):
            state = "invalid_evidence"
        states[criterion_id] = state
    return states


def _roadmap_phase_criteria(roadmap_text: str) -> list[tuple[int, str, list[str]]]:
    """Extract explicit criterion IDs from each numbered Cognitive Roadmap phase."""
    lines = roadmap_text.splitlines()
    phases: list[tuple[int, str, list[str]]] = []
    for index, heading in enumerate(lines):
        if not heading.startswith("## "):
            continue
        phase_match = re.search(r"\bFase\s+([0-8])\b", heading, re.IGNORECASE)
        if phase_match is None:
            continue
        phase_number = int(phase_match.group(1))
        end = next(
            (
                position
                for position in range(index + 1, len(lines))
                if lines[position].startswith("## ")
            ),
            len(lines),
        )
        section = "\n".join(lines[index:end])
        pattern = re.compile(rf"`(C{phase_number}-[A-Z0-9]+(?:-[A-Z0-9]+)*)`")
        criterion_ids = list(dict.fromkeys(pattern.findall(section)))
        if criterion_ids:
            phases.append((phase_number, heading[3:].strip(), criterion_ids))
    return sorted(phases, key=lambda item: item[0])


def roadmap_candidates(roadmap_text: str, status_text: str, limit: int = 5) -> list[str]:
    """Report the first incomplete roadmap phase using STATUS evidence.

    The roadmap defines the criteria; STATUS supplies their current evidence
    state. Missing or invalid records remain unknown and therefore cannot be
    silently skipped.
    """
    if not roadmap_text.strip():
        return ["docs/COGNITIVE_ROADMAP.md ausente; nenhum critério foi considerado concluído."]
    phases = _roadmap_phase_criteria(roadmap_text)
    if not phases:
        return ["Nenhum critério com ID explícito foi encontrado em docs/COGNITIVE_ROADMAP.md."]

    states = _status_criterion_states(status_text)
    for _phase_number, heading, criterion_ids in phases:
        incomplete = [
            (criterion_id, states.get(criterion_id, "unknown"))
            for criterion_id in criterion_ids
            if states.get(criterion_id) != "verified"
        ]
        if not incomplete:
            continue
        visible = incomplete[: max(1, limit)]
        details = "; ".join(f"`{criterion_id}`: {state}" for criterion_id, state in visible)
        omitted = len(incomplete) - len(visible)
        if omitted:
            details += f"; mais {omitted} critério(s) pendente(s) não exibido(s)"
        return [f"- **{heading}** — {details}"]

    return [
        "Todos os critérios com ID explícito estão marcados como verified no ledger; "
        "isso não substitui revisão humana nem verificação de runtime/produção."
    ]

def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status_text = STATUS.read_text(encoding="utf-8") if STATUS.exists() else ""
    roadmap_text = ROADMAP.read_text(encoding="utf-8") if ROADMAP.exists() else ""
    tests = TEST_LOG.read_text(encoding="utf-8", errors="replace") if TEST_LOG.exists() else "pytest não executado."
    test_lines = [line.strip() for line in tests.splitlines() if re.search(r"\b(passed|failed|error|skipped|no tests ran)\b", line, re.I)]
    test_summary = test_lines[-5:] or ["Não foi possível extrair um resumo do log de pytest."]

    tracked = git_lines("ls-files", "*.py")
    markers: list[str] = []
    patterns = re.compile(r"\b(TODO|FIXME|XXX|NotImplementedError)\b")
    for rel in tracked:
        if any(part in rel for part in (".venv/", "vendor/")):
            continue
        path = ROOT / rel
        try:
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if patterns.search(line):
                    markers.append(f"- `{rel}:{number}`: {line.strip()[:180]}")
                    if len(markers) >= 80:
                        break
        except OSError:
            continue
        if len(markers) >= 80:
            break

    recent = git_lines("log", "-5", "--date=short", "--pretty=format:%h %ad %s")
    sections = [
        "# JARVIS — relatório horário de curiosidade",
        f"\n**Gerado:** {now}",
        "\n> Auditoria somente leitura. Nenhum arquivo de produção é alterado, nenhum patch é aplicado e nenhuma PR é criada automaticamente.",
        "\n## Resultado dos testes",
        *[f"- {line}" for line in test_summary],
        "\n## Próximas trilhas do roadmap",
        *roadmap_candidates(roadmap_text, status_text),
        "\n## Marcadores de trabalho encontrados (amostra limitada a 80)",
        *(markers or ["Nenhum marcador TODO/FIXME/XXX/NotImplementedError encontrado nos arquivos Python rastreados."]),
        "\n## Commits recentes para investigação",
        *[f"- {line}" for line in recent],
        "\n## Próximas ações sugeridas",
        "- Investigar primeiro falhas de teste reproduzíveis; incluir teste de regressão antes de corrigir.",
        "- Para cada otimização, registrar evidência, impacto esperado, risco e teste de aceitação.",
        "- Selecionar a primeira trilha parcial do roadmap cujas dependências e critérios possam ser verificados; não marcar como concluída sem evidência.",
        "- Mudanças de código devem seguir branch isolada, PR e CI verde; não desabilitar testes.",
    ]
    REPORT.write_text("\n".join(sections) + "\n", encoding="utf-8")
    print(f"Relatório escrito em {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
