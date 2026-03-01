# -*- coding: utf-8 -*-
import os
import json
import shutil
import re
from pathlib import Path

REPO_ROOT = Path(".").resolve()
FROZEN_ROOT = REPO_ROOT / ".frozen"
FROZEN_INDEX = FROZEN_ROOT / "frozen_index.json"
FROZEN_DIRS = [FROZEN_ROOT / "caps", FROZEN_ROOT / "others"]

IMMUTABLE_PATHS = [
    "app/core", "app/runtime", "app/bootstrap", "tests", 
    "docs", "scripts", "dags", "__init__.py", "setup.py"
]

def is_immutable(rel_path: str) -> bool:
    return any(rel_path.startswith(p) or rel_path == p for p in IMMUTABLE_PATHS)

def load_index():
    if not FROZEN_INDEX.exists(): return {}
    try: return json.loads(FROZEN_INDEX.read_text())
    except: return {}

def discover_used_modules():
    used = set()
    pattern = re.compile(r'[a-zA-Z0-9_\-\.]+') 
    for cfg in REPO_ROOT.rglob("*"):
        if ".frozen" in str(cfg) or ".git" in str(cfg) or "__pycache__" in str(cfg): continue
        if cfg.is_file() and cfg.suffix in [".yml", ".yaml", ".json", ".py", ".md"]:
            try:
                content = cfg.read_text(encoding="utf-8")
                used.update(pattern.findall(content))
                used.add(cfg.stem)
            except: continue
    return used

def unfreeze_used(index: dict, used_modules: set):
    print("🔥 [ACTION] Tentando descongelar módulos...")
    for key_name, meta in list(index.items()):
        # Extrai o nome real do arquivo (ex: infrastructure/drive_uploader.py -> drive_uploader.py)
        file_name = os.path.basename(key_name)
        stem = Path(file_name).stem
        
        possible_matches = {file_name, stem, key_name, Path(meta["original_path"]).stem}
        
        if any(m in used_modules for m in possible_matches):
            found_path = None
            # Tenta achar o arquivo físico de 3 formas: nome limpo, nome da chave, ou nome no meta
            search_targets = [file_name, key_name, os.path.basename(meta["original_path"])]
            
            for d in FROZEN_DIRS:
                for target in search_targets:
                    p = d / target
                    if p.exists():
                        found_path = p
                        break
                if found_path: break

            if found_path:
                dest = REPO_ROOT / meta["original_path"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(found_path), str(dest))
                del index[key_name]
                print(f"✅ [UNFROZEN] {file_name} -> {meta['original_path']}")
            else:
                print(f"⚠️ [STILL MISSING] {file_name} (Chave: {key_name})")

def freeze_file(rel_path: str, index: dict):
    src = REPO_ROOT / rel_path
    if not src.exists() or "__init__" in rel_path: return
    is_cap = "capabilities" in rel_path or "gears" in rel_path or src.name.startswith("cap_")
    dst_folder = FROZEN_ROOT / ("caps" if is_cap else "others")
    dst_folder.mkdir(parents=True, exist_ok=True)
    
    # Salva sempre com o nome limpo do arquivo para evitar confusão
    dst = dst_folder / src.name
    shutil.move(str(src), str(dst))
    index[src.name] = {"original_path": rel_path, "type": "capability" if is_cap else "other"}
    print(f"🧊 [FROZEN] {rel_path}")

def main():
    print("="*60 + "\nJARVIS REPO GOVERNANCE - RECOVERY MODE\n" + "="*60)
    index = load_index()
    used = discover_used_modules()
    unfreeze_used(index, used)

    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))
        if is_immutable(rel) or ".frozen" in rel: continue
        if py.name not in used and py.stem not in used:
            freeze_file(rel, index)
    
    FROZEN_INDEX.write_text(json.dumps(index, indent=2))
    print("="*60 + "\nGOVERNANÇA CONCLUÍDA.\n" + "="*60)

if __name__ == "__main__":
    main()
