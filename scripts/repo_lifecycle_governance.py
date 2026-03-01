# -*- coding: utf-8 -*-
import os
import ast
import json
import shutil
import yaml  # Certifique-se de ter PyYAML instalado
from pathlib import Path

REPO_ROOT = Path(".").resolve()

# Configurações de Frozen
FROZEN_ROOT = REPO_ROOT / ".frozen"
FROZEN_CAPS = FROZEN_ROOT / "caps"
FROZEN_OTHERS = FROZEN_ROOT / "others"
FROZEN_INDEX = FROZEN_ROOT / "frozen_index.json"

IMMUTABLE_PATHS = [
    "app/core",
    "app/runtime",
    "app/bootstrap",
    "tests",
    "docs",
    "scripts",
    "dags",
    "__init__.py",
    "setup.py",
    "build_config.py",
]

CAPABILITY_MARKERS = [
    "/capabilities/",
    "/gears/",
]

def is_immutable(rel_path: str) -> bool:
    return any(rel_path.startswith(p) or rel_path == p for p in IMMUTABLE_PATHS)

def is_capability(rel_path: str) -> bool:
    return (
        any(m in rel_path for m in CAPABILITY_MARKERS)
        or Path(rel_path).name.startswith("cap_")
    )

def load_index():
    if not FROZEN_INDEX.exists():
        return {}
    try:
        return json.loads(FROZEN_INDEX.read_text())
    except:
        return {}

def save_index(index):
    FROZEN_ROOT.mkdir(exist_ok=True)
    FROZEN_CAPS.mkdir(exist_ok=True)
    FROZEN_OTHERS.mkdir(exist_ok=True)
    FROZEN_INDEX.write_text(json.dumps(index, indent=2))

# ---------------------------------------------------------------------
# NOVA LÓGICA DE DESCOBERTA
# ---------------------------------------------------------------------

def discover_used_modules():
    """Varre arquivos .py (AST) e .yml/.yaml (Texto/Estrutura) em busca de módulos usados."""
    used = set()

    # 1. Varredura em arquivos Python (Lógica Original)
    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))
        if is_immutable(rel) or ".frozen" in rel:
            continue

        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        used.add(n.name.split(".")[0])
                        used.add(n.name.split(".")[-1]) # Pega o nome final do módulo
                elif isinstance(node, ast.ImportFrom) and node.module:
                    used.add(node.module.split(".")[0])
                    # Adiciona também os nomes específicos importados (ex: drive_uploader)
                    for n in node.names:
                        used.add(n.name)
        except Exception:
            continue

    # 2. Varredura em arquivos YAML (Pipelines e Configurações)
    # Procuramos por strings que correspondam a IDs de componentes
    for yml in REPO_ROOT.rglob("*.y*ml"):
        rel = str(yml.relative_to(REPO_ROOT))
        if ".frozen" in rel:
            continue
            
        try:
            content = yml.read_text(encoding="utf-8")
            # Extração simples via string: se o nome do componente aparece no YAML, ele está em uso.
            # Isso cobre casos como 'step: drive_uploader' ou 'target: drive_uploader'
            data = yaml.safe_load(content)
            
            # Função recursiva para pegar todas as strings dentro do YAML
            def extract_strings(obj):
                if isinstance(obj, str):
                    used.add(obj)
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        used.add(k) # Às vezes o ID é uma chave
                        extract_strings(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_strings(item)
            
            extract_strings(data)
        except Exception as e:
            # Fallback para regex simples se o YAML estiver mal formatado
            import re
            words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]+', content)
            used.update(words)

    return used

# ---------------------------------------------------------------------

def freeze_file(rel_path: str, index: dict):
    src = REPO_ROOT / rel_path
    if not src.exists(): return
    
    name = src.name
    dst_folder = FROZEN_CAPS if is_capability(rel_path) else FROZEN_OTHERS
    dst = dst_folder / name

    if dst.exists(): return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    index[name] = {
        "original_path": rel_path,
        "type": "capability" if is_capability(rel_path) else "other",
    }
    print(f"🧊 FROZEN: {rel_path}")

def unfreeze_used(index: dict, used_modules: set):
    restored = []
    for name, meta in list(index.items()):
        module_name = Path(name).stem
        
        # Se o nome do arquivo ou o nome do módulo (sem .py) está na lista de usados
        if module_name in used_modules or name in used_modules:
            original = REPO_ROOT / meta["original_path"]
            frozen_path = (FROZEN_CAPS / name if meta["type"] == "capability" else FROZEN_OTHERS / name)

            if frozen_path.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(frozen_path), str(original))
                restored.append(name)
                del index[name]
                print(f"🔥 UNFROZEN: {name}")
    return restored

def main():
    print("=" * 80)
    print("Jarvis Governance — YAML-AWARE DISCOVERY")
    print("=" * 80)

    index = load_index()
    used = discover_used_modules()

    # Garantir que IDs conhecidos do sistema nunca sejam congelados
    # used.add("drive_uploader") # Exemplo de trava manual se necessário

    print(f"[DISCOVERY] Itens detectados em uso: {len(used)}")

    unfreeze_used(index, used)

    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))
        if is_immutable(rel) or ".frozen" in rel:
            continue

        if not is_capability(rel):
            continue

        name = py.stem
        if name not in used:
            freeze_file(rel, index)

    save_index(index)
    print("-" * 80)
    print("Governança concluída com sucesso.")

if __name__ == "__main__":
    main()
