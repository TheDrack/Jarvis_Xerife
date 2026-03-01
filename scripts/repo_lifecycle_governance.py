# -*- coding: utf-8 -*-
import os
import ast
import json
import shutil
import re
from pathlib import Path

REPO_ROOT = Path(".").resolve()
FROZEN_ROOT = REPO_ROOT / ".frozen"
FROZEN_INDEX = FROZEN_ROOT / "frozen_index.json"

# Pastas onde os arquivos congelados estão de fato
FROZEN_DIRS = [FROZEN_ROOT / "caps", FROZEN_ROOT / "others"]

IMMUTABLE_PATHS = [
    "app/core", "app/runtime", "app/bootstrap", "tests", 
    "docs", "scripts", "dags", "__init__.py", "setup.py", "build_config.py"
]

def is_immutable(rel_path: str) -> bool:
    return any(rel_path.startswith(p) or rel_path == p for p in IMMUTABLE_PATHS)

def load_index():
    if not FROZEN_INDEX.exists(): 
        print("⚠️ [INDEX] Arquivo frozen_index.json não encontrado!")
        return {}
    try: 
        data = json.loads(FROZEN_INDEX.read_text())
        print(f"📂 [INDEX] {len(data)} arquivos registrados no gelo.")
        return data
    except Exception as e: 
        print(f"❌ [INDEX] Erro ao ler índice: {e}")
        return {}

def discover_used_modules():
    used = set()
    # Pattern que aceita quase tudo que pode ser um ID ou nome de arquivo
    pattern = re.compile(r'[a-zA-Z0-9_\-\.]+') 

    print("🔍 [SCAN] Iniciando varredura de arquivos ativos...")
    for cfg in REPO_ROOT.rglob("*"):
        # Ignora a pasta .frozen e pastas de sistema
        if ".frozen" in str(cfg) or ".git" in str(cfg) or "__pycache__" in str(cfg):
            continue
            
        if cfg.is_file() and cfg.suffix in [".yml", ".yaml", ".json", ".py", ".md", ".txt"]:
            try:
                content = cfg.read_text(encoding="utf-8")
                matches = pattern.findall(content)
                used.update(matches)
                # Adiciona o nome do próprio arquivo (sem extensão) como usado
                used.add(cfg.stem)
            except: continue
    return used

def unfreeze_used(index: dict, used_modules: set):
    print("🔥 [ACTION] Tentando descongelar módulos...")
    restored_count = 0
    
    for name, meta in list(index.items()):
        stem = Path(name).stem
        # Tenta várias combinações para garantir o match
        # drive_uploader.py, drive_uploader, ou o caminho original
        possible_matches = {name, stem, meta["original_path"], Path(meta["original_path"]).stem}
        
        if any(m in used_modules for m in possible_matches):
            # Tenta localizar o arquivo nas pastas de gelo
            found_frozen = None
            for d in FROZEN_DIRS:
                path = d / name
                if path.exists():
                    found_frozen = path
                    break
            
            if found_frozen:
                original_path = REPO_ROOT / meta["original_path"]
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(found_frozen), str(original_path))
                del index[name]
                print(f"✅ [UNFROZEN] {name} -> {meta['original_path']}")
                restored_count += 1
            else:
                print(f"⚠️ [MISSING] {name} está no índice mas o arquivo físico sumiu de .frozen/")
    
    if restored_count == 0:
        print("ℹ️ Ninguém foi descongelado nesta rodada.")

def freeze_file(rel_path: str, index: dict):
    src = REPO_ROOT / rel_path
    if not src.exists(): return
    
    # Define se é capability
    is_cap = "capabilities" in rel_path or "gears" in rel_path or src.name.startswith("cap_")
    dst_folder = FROZEN_ROOT / ("caps" if is_cap else "others")
    dst_folder.mkdir(parents=True, exist_ok=True)
    
    dst = dst_folder / src.name
    shutil.move(str(src), str(dst))
    
    index[src.name] = {
        "original_path": rel_path, 
        "type": "capability" if is_cap else "other"
    }
    print(f"🧊 [FROZEN] {rel_path}")

def main():
    print("="*60)
    print("JARVIS REPO GOVERNANCE - PROTOCOLO SIMBIOSE")
    print("="*60)
    
    index = load_index()
    used = discover_used_modules()
    
    print(f"📊 [STATS] {len(used)} tokens de uso detectados.")
    
    # DEBUG ESPECÍFICO
    if "drive_uploader" in used:
        print("🎯 DEBUG: A string 'drive_uploader' FOI encontrada no repositório!")
    else:
        print("❓ DEBUG: A string 'drive_uploader' NÃO foi encontrada nos arquivos ativos.")

    unfreeze_used(index, used)

    # Varre para congelar apenas se não estiver em uso
    for py in REPO_ROOT.rglob("*.py"):
        rel = str(py.relative_to(REPO_ROOT))
        if is_immutable(rel) or ".frozen" in rel or "__init__" in rel:
            continue
        
        # Se nem o nome do arquivo nem o stem estão nos tokens usados
        if py.name not in used and py.stem not in used:
            freeze_file(rel, index)
    
    # Salva o índice atualizado
    FROZEN_ROOT.mkdir(exist_ok=True)
    FROZEN_INDEX.write_text(json.dumps(index, indent=2))
    print("="*60)
    print("GOVERNANÇA CONCLUÍDA.")
    print("="*60)

if __name__ == "__main__":
    main()
