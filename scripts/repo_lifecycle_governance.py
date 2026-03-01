# -*- coding: utf-8 -*-
import os
import ast
import json
import shutil
import re
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

def is_immutable(rel_path: str) -> bool:
    return any(rel_path.startswith(p) or rel_path == p for p in IMMUTABLE_PATHS)

def load_index():
    if not FROZEN_INDEX.exists(): return {}
    try: return json.loads(FROZEN_INDEX.read_text())
    except: return {}

def save_index(index):
    for p in [FROZEN_CAPS, FROZEN_OTHERS]: p.mkdir(parents=True, exist_ok=True)
    FROZEN_INDEX.write_text(json.dumps(index, indent=2))

def discover_used_modules():
    used = set()
    # Padrão expandido: aceita nomes de arquivos, ids e referências de pipeline
    # Captura drive_uploader, sync_drive, etc.
    pattern = re.compile(r'[a-zA-Z0-9_\-]{3,}') 

    for cfg in REPO_ROOT.rglob("*"):
        # Varre YAML, JSON, TOML e também os próprios scripts Python em busca de strings
        if cfg.suffix in [".yml", ".yaml", ".json", ".toml", ".py"] and ".frozen" not in str(cfg):
            try:
                content = cfg.read_text(encoding="utf-8")
                matches = pattern.findall(content)
                used.update(matches)
                
                # Se for Python, faz um parse AST extra para garantir imports
                if cfg.suffix == ".py":
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.Import, ast.ImportFrom)):
                            for n in node.names:
                                used.add(n.name.split(".")[-1])
                                if isinstance(node, ast.ImportFrom) and node.module:
                                    used.add(node.module.split(".")[-1])
            except: continue
    return used

def unfreeze_used(index: dict, used_modules: set):
    """
    Regra de Ouro: Se o nome do arquivo (com ou sem .py) foi citado em QUALQUER 
    configuração ou código, ele deve ser trazido de volta.
    """
    for name, meta in list(index.items()):
        stem = Path(name).stem
        
        # BUSCA EXAUSTIVA: Verifica se o ID original ou o nome do arquivo foi citado
        if stem in used_modules or name in used_modules:
            original_path = Path(meta["original_path"])
            frozen_path = (FROZEN_CAPS / name if meta["type"] == "capability" else FROZEN_OTHERS / name)

            if frozen_path.exists():
                (REPO_ROOT / original_path.parent).mkdir(parents=True, exist_ok=True)
                shutil.move(str(frozen_path), str(REPO_ROOT / original_path))
                del index[name]
                print(f"🔥 UNFROZEN: {name} (Restaurado para {original_path})")

def freeze_file(rel_path: str, index: dict):
    src = REPO_ROOT / rel_path
    if not src.exists(): return
    
    # Define se é capability pelo caminho ou prefixo
    is_cap = "capabilities" in rel_path or "gears" in rel_path or src.name.startswith("cap_")
    dst = (FROZEN_CAPS if is_cap else FROZEN_OTHERS) / src.name
    
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    index[src.name] = {
        "original_path": rel_path, 
        "type": "capability" if is_cap else "other"
    }
    print(f"🧊 FROZEN: {rel_path}")

def main():
    print("="*60 + "\nJarvis Governance — DEEP SEARCH MODE\n" + "="*60)
    index = load_index()
    used = discover_used_modules()
    
    # Forçar IDs críticos se necessário (Safety Net)
    # used.add("drive_uploader") 

    print(f"[DISCOVERY] {len(used)} tokens found in repository configs.")
    unfreeze_used(index, used)

    # Nova varredura para congelar o que SOBROU e não é imutável
    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))
        if is_immutable(rel) or ".frozen" in rel: continue
        
        # Se o arquivo não foi citado em lugar nenhum, congela
        if py.stem not in used and py.name not in used:
            freeze_file(rel, index)
    
    save_index(index)
    print("="*60 + "\nGovernance complete.\n" + "="*60)

if __name__ == "__main__":
    main()
