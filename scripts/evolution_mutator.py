# -*- coding: utf-8 -*-
import argparse
import os
import sys
import json
import re
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

def get_entry_from_crystal(cap_id: str, crystal_path="data/master_crystal.json"):
    path = Path(crystal_path)
    if not path.exists(): return None
    with open(path, 'r', encoding='utf-8') as f:
        crystal = json.load(f)
    for entry in crystal.get("registry", []):
        if entry["id"] == cap_id: return entry
    return None

def evolve():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()

    core = MetabolismCore()
    issue_body = os.getenv('ISSUE_BODY', '')
    match = re.search(r'(CAP-\d+)', issue_body)
    if not match: sys.exit(1)
    
    cap_id = match.group(1)
    entry = get_entry_from_crystal(cap_id)
    if not entry: sys.exit(1)

    target_file = entry["genealogy"]["target_file"]
    path = Path(target_file)
    current_code = path.read_text(encoding='utf-8') if path.exists() else ""

    system_prompt = (
        "Você é o Engenheiro Senior do JARVIS. Implemente a lógica completa.\n"
        f"Arquivo: {target_file} | Setor: {entry['sector']}\n"
        "Responda APENAS JSON: {\"code\": \"...\", \"summary\": \"...\"}"
    )
    user_prompt = f"MISSÃO: {issue_body}\nCONTEXTO: {args.roadmap_context}\nCÓDIGO BASE:\n{current_code}"

    try:
        response = core.ask_jarvis(system_prompt, user_prompt)
        from scripts.evolution_mutator import clean_json_response # Reutilizando sua função de limpeza
        mutation = clean_json_response(response)
        new_code = mutation.get('code', '')
        if len(new_code.strip()) > 50:
            path.write_text(new_code, encoding='utf-8')
            print(f"✅ Mutação aplicada no setor {entry['sector']}: {target_file}")
        else:
            sys.exit(1)
    except Exception as e:
        print(f"❌ Erro: {e}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
