# -*- coding: utf-8 -*-
"""
fix_cap_stubs.py — Corrige arquivos cap_NNN.py gerados com templates não expandidos.

Detecta arquivos que contêm os marcadores literais `{cap['id']}` ou `{target_dir}`
(bug do gerador original), substitui pelos valores reais derivados do nome do arquivo
e de data/capabilities.json, e atualiza o docstring com o título e descrição reais.

Arquivos com mais de 20 linhas e sem os marcadores de stub são preservados intactos.
"""
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

CAPS_DIR = Path("app/domain/capabilities")
CAPS_JSON = Path("data/capabilities.json")
STUB_MARKERS = ["{cap['id']}", "{target_dir}"]

STUB_TEMPLATE = '''\
# -*- coding: utf-8 -*-
from app.core.nexuscomponent import NexusComponent


class {class_name}(NexusComponent):
    """
    Capability: {title}
    ID: {cap_id}
    Setor: {sector}
    Descrição: {description}
    """

    def __init__(self):
        super().__init__()
        self.cap_id = "{cap_id}"
        self.title = "{title}"
        self.active = True

    def configure(self, config: dict = None):
        """Configuração opcional via Pipeline YAML."""
        if config:
            self.active = config.get("active", True)

    def execute(self, context: dict = None) -> dict:
        """Execução lógica principal.

        Retorna evidência de efeito conforme contrato NexusComponent.
        """
        if context is None:
            context = {{}}

        cap_id = self.cap_id
        title = self.title
        active = self.active

        if not active:
            return {{"success": False, "cap_id": cap_id, "reason": "componente inativo"}}

        result = {{
            "cap_id": cap_id,
            "title": title,
            "status": "executed",
            "context_keys": list(context.keys()),
        }}
        return {{"success": True, "result": result}}
'''


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _load_caps_index(caps_json: Path) -> Dict[str, Dict]:
    """Retorna um dict {cap_id: cap_data} a partir de capabilities.json."""
    if not caps_json.exists():
        print(f"⚠️  {caps_json} não encontrado — usando metadados mínimos.")
        return {}
    with open(caps_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {c["id"]: c for c in data.get("capabilities", [])}


def _file_to_cap_id(file_path: Path) -> str:
    """cap_042.py → CAP-042"""
    num = file_path.stem.replace("cap_", "")
    return f"CAP-{num}"


def _file_to_class_name(file_path: Path) -> str:
    """cap_042.py → Cap042"""
    num = file_path.stem.replace("cap_", "")
    return f"Cap{num}"


def _is_stub(content: str) -> bool:
    return any(marker in content for marker in STUB_MARKERS)


def _has_real_implementation(content: str) -> bool:
    """Considera 'real' qualquer arquivo com mais de 20 linhas e sem marcadores."""
    lines = [ln for ln in content.splitlines() if ln.strip()]
    return len(lines) > 20 and not _is_stub(content)


# ---------------------------------------------------------------------------
# Processamento de cada arquivo
# ---------------------------------------------------------------------------

def _fix_file(file_path: Path, caps_index: Dict[str, Dict]) -> bool:
    """
    Substitui o conteúdo stub pelo template correto.
    Retorna True se o arquivo foi modificado.
    """
    content = file_path.read_text(encoding="utf-8")

    if _has_real_implementation(content):
        return False  # Preserva sem modificar

    if not _is_stub(content):
        return False  # Sem marcadores — não toca

    cap_id = _file_to_cap_id(file_path)
    class_name = _file_to_class_name(file_path)
    num = file_path.stem.replace("cap_", "")
    sector = f"app/domain/capabilities/cap_{num}.py"

    cap_data = caps_index.get(cap_id, {})
    title = cap_data.get("title", f"Capability {cap_id}")
    description = cap_data.get("description", "Sem descrição disponível.")

    new_content = STUB_TEMPLATE.format(
        class_name=class_name,
        cap_id=cap_id,
        sector=sector,
        title=title,
        description=description,
    )

    file_path.write_text(new_content, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    caps_index = _load_caps_index(CAPS_JSON)

    stub_files = sorted(CAPS_DIR.glob("cap_*.py"))
    if not stub_files:
        print(f"⚠️  Nenhum arquivo cap_*.py encontrado em {CAPS_DIR}.")
        sys.exit(0)

    fixed = 0
    skipped = 0
    total = 0

    for file_path in stub_files:
        if file_path.name == "__init__.py":
            continue
        total += 1
        cap_id = _file_to_cap_id(file_path)
        try:
            modified = _fix_file(file_path, caps_index)
            if modified:
                fixed += 1
                print(f"✅ Corrigido: {file_path.name} ({cap_id})")
            else:
                skipped += 1
        except Exception as exc:
            print(f"❌ Erro em {file_path.name}: {exc}")

    print(
        f"\n📊 Resumo: {total} arquivos analisados, "
        f"{fixed} corrigidos, {skipped} preservados."
    )


if __name__ == "__main__":
    main()
