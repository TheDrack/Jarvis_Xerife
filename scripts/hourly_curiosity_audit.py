#!/usr/bin/env python3
"""Read-only hourly curiosity audit: roadmap, unfinished markers, and test outcome."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "STATUS.md"
REPORT_DIR = ROOT / "audit-output"
REPORT = REPORT_DIR / "hourly-curiosity-report.md"
TEST_LOG = REPORT_DIR / "pytest.log"


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.splitlines() if result.returncode == 0 else []


def roadmap_candidates(text: str) -> list[str]:
    section = text.split("## Roadmap", 1)
    if len(section) < 2:
        return ["Não foi possível localizar a seção 'Roadmap' em docs/STATUS.md."]
    lines = section[1].splitlines()
    candidates: list[str] = []
    for line in lines:
        if line.startswith("## "):
            break
        if not line.startswith("|") or "---" in line or "Fase / trilha" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        status = cells[1].lower()
        if any(term in status for term in ("parcial", "progresso", "pendente", "requer")):
            candidates.append(f"- **{cells[0]}** — {cells[1]}. Critério: {cells[2]}")
    return candidates[:5] or ["Nenhuma trilha parcial foi identificada automaticamente; revisar STATUS.md."]


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status_text = STATUS.read_text(encoding="utf-8") if STATUS.exists() else ""
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
        *roadmap_candidates(status_text),
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
