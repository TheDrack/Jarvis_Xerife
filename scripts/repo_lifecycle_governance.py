# -*- coding: utf-8 -*-
import os
import json
import shutil
import re
from pathlib import Path

REPO_ROOT = Path(".").resolve()
FROZEN_ROOT = REPO_ROOT / ".frozen"
FROZEN_INDEX = FROZEN_ROOT / "frozen_index.json"

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
    # Captura tokens, caminhos parciais e nomes de arquivos
    pattern = re.compile(r'[a-zA-Z0-9_\-\.\/]+') 
    for cfg in REPO_ROOT.rglob("*"):
        if ".frozen" in str(cfg) or ".git" in str(cfg) or "__pycache__" in str(cfg): continue
        if cfg.is_file() and cfg.suffix in [".yml", ".yaml", ".json", ".py", ".md"]:
            try:
                content = cfg.read_text(encoding="utf-8")
                used.update(pattern.findall(content))
                used.add(cfg.stem)
                used.add(cfg.name)
            except: continue
    return used

def find_file_in_frozen(target_name):
    """Busca recursivamente por um arquivo dentro da pasta .frozen"""
    if not FROZEN_ROOT.exists(): return None
    for root, _, files in os.walk(FROZEN_ROOT):
        if target_name in files:
            return Path(root) / target_name
    return None

def unfreeze_used(index: dict, used_modules: set):
    print("🔥 [ACTION] Iniciando Resgate em Deep-Freeze...")
    restored_count = 0

    for key_name, meta in list(index.items()):
        # Nome base do arquivo (ex: drive_uploader.py)
        file_name = os.path.basename(key_name)
        stem = Path(file_name).stem

        # Critérios de match: se o nome, o stem ou a chave do índice aparecem nos usados
        if any(m in used_modules for m in [file_name, stem, key_name]):
            # BUSCA GLOBAL RECURSIVA dentro de .frozen
            found_path = find_file_in_frozen(file_name)

            if found_path:
                dest = REPO_ROOT / meta["original_path"]
                dest.parent.mkdir(parents=True, exist_ok=True)

                shutil.move(str(found_path), str(dest))
                del index[key_name]
                print(f"✅ [UNFROZEN] {file_name} -> {meta['original_path']}")
                restored_count += 1
            else:
                # Se não achou pelo nome da chave, tenta pelo nome do arquivo original no meta
                alt_name = os.path.basename(meta["original_path"])
                found_path = find_file_in_frozen(alt_name)
                if found_path:
                    dest = REPO_ROOT / meta["original_path"]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(found_path), str(dest))
                    del index[key_name]
                    print(f"✅ [UNFROZEN] {alt_name} -> {meta['original_path']}")
                    restored_count += 1
                else:
                    print(f"⚠️ [NOT FOUND IN FROZEN] {file_name} (Deveria estar em .frozen/)")

    if restored_count == 0:
        print("ℹ️ Nenhum arquivo pendente para descongelamento foi localizado fisicamente.")

def main():
    print("="*60 + "\nJARVIS REPO GOVERNANCE - RECURSIVE RECOVERY\n" + "="*60)
    index = load_index()
    used = discover_used_modules()

    unfreeze_used(index, used)

    # Limpeza: remove pastas vazias em .frozen após o unfreeze
    if FROZEN_ROOT.exists():
        for root, dirs, files in os.walk(FROZEN_ROOT, topdown=False):
            for name in dirs:
                dir_path = os.path.join(root, name)
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)

    FROZEN_INDEX.write_text(json.dumps(index, indent=2))
    print("="*60 + "\nGOVERNANÇA CONCLUÍDA.\n" + "="*60)

if __name__ == "__main__":
    main()
