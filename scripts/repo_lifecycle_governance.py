# -*- coding: utf-8 -*-
import os
import ast
import json
import shutil
import re  # Nativo, substitui o PyYAML para evitar ModuleNotFoundError
from pathlib import Path

REPO_ROOT = Path(".").resolve()

FROZEN_ROOT = REPO_ROOT / ".frozen"
FROZEN_CAPS = FROZEN_ROOT / "caps"
FROZEN_OTHERS = FROZEN_ROOT / "others"
FROZEN_INDEX = FROZEN_ROOT / "frozen_index.json"

IMMUTABLE_PATHS = [
    "app/core", "app/runtime", "app/bootstrap", "tests", 
    "docs", "scripts", "dags", "__init__.py", "setup.py", "build_config.py"
]

CAPABILITY_MARKERS = ["/capabilities/", "/gears/"]

def is_immutable(rel_path: str) -> bool:
    return any(rel_path.startswith(p) or rel_path == p for p in IMMUTABLE_PATHS)

def is_capability(rel_path: str) -> bool:
    return any(m in rel_path for m in CAPABILITY_MARKERS) or Path(rel_path).name.startswith("cap_")

def load_index():
    if not FROZEN_INDEX.exists(): return {}
    try: return json.loads(FROZEN_INDEX.read_text())
    except: return {}

def save_index(index):
    for p in [FROZEN_CAPS, FROZEN_OTHERS]: p.mkdir(parents=True, exist_ok=True)
    FROZEN_INDEX.write_text(json.dumps(index, indent=2))

def discover_used_modules():
    used = set()
    # Padrão para capturar nomes de módulos/ids em YAML e Python
    pattern = re.compile(r'[a-zA-Z_][a-zA-Z0-9_]{3,}') 

    # 1. Varredura em arquivos Python (AST para precisão)
    for py in REPO_ROOT.rglob("*.py"):
        if is_immutable(str(py.relative_to(REPO_ROOT))) or ".frozen" in str(py): continue
        try:
            content = py.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        used.update([n.name.split(".")[0], n.name.split(".")[-1]])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    used.add(node.module.split(".")[0])
                    for n in node.names: used.add(n.name)
        except: continue

    # 2. Varredura em YAML e Configurações (Regex para compatibilidade total)
    for cfg in REPO_ROOT.rglob("*"):
        if cfg.suffix in [".yml", ".yaml", ".json", ".toml"] and ".frozen" not in str(cfg):
            try:
                matches = pattern.findall(cfg.read_text(encoding="utf-8"))
                used.update(matches)
            except: continue
    return used

def freeze_file(rel_path: str, index: dict):
    src = REPO_ROOT / rel_path
    if not src.exists(): return
    dst = (FROZEN_CAPS if is_capability(rel_path) else FROZEN_OTHERS) / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    index[src.name] = {"original_path": rel_path, "type": "capability" if is_capability(rel_path) else "other"}
    print(f"🧊 FROZEN: {rel_path}")

def unfreeze_used(index: dict, used_modules: set):
    for name, meta in list(index.items()):
        stem = Path(name).stem
        if stem in used_modules or name in used_modules:
            original = REPO_ROOT / meta["original_path"]
            frozen = (FROZEN_CAPS / name if meta["type"] == "capability" else FROZEN_OTHERS / name)
            if frozen.exists():
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(frozen), str(original))
                del index[name]
                print(f"🔥 UNFROZEN: {name}")

def main():
    print("="*60 + "\nJarvis Governance — Resilient Mode\n" + "="*60)
    index = load_index()
    used = discover_used_modules()
    print(f"[DISCOVERY] {len(used)} potencial tokens in use.")
    unfreeze_used(index, used)

    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))
        if is_immutable(rel) or ".frozen" in rel or not is_capability(rel): continue
        if py.stem not in used: freeze_file(rel, index)
    
    save_index(index)
    print("="*60 + "\nGovernance complete.\n" + "="*60)

if __name__ == "__main__":
    main()
