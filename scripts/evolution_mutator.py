# -*- coding: utf-8 -*-
import argparse
import os
import sys
import json
import re
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

def clean_json_response(raw_response):
    if isinstance(raw_response, dict): return raw_response
    clean_text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', raw_response, flags=re.DOTALL)
    clean_text = clean_text.strip()
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        match = re.search(r'(\{.*\})', clean_text, re.DOTALL)
        if match: return json.loads(match.group(1))
        raise ValueError("Falha crítica ao parsear resposta da IA")

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

    # Prompt ultra-diretivo para evitar respostas vazias
    system_prompt = (
        f"Você é o JARVIS. Implemente a lógica da {cap_id} ({entry['title']}).\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Escreva o código completo do arquivo Python.\n"
        "2. O código deve conter obrigatoriamente 'def execute(context=None):'.\n"
        "3. Importe bibliotecas necessárias (time, os, psutil, etc).\n"
        "4. Responda APENAS um JSON no formato: {\"code\": \"...\", \"summary\": \"...\"}"
    )
    user_prompt = f"MISSÃO: {issue_body}\nCÓDIGO ATUAL:\n{current_code}"

    try:
        print(f"🧬 Mutando {cap_id} no setor {entry['sector']}...")
        response = core.ask_jarvis(system_prompt, user_prompt)
        mutation = clean_json_response(response)
        new_code = mutation.get('code', '')
        
        # Validação Funcional em vez de tamanho fixo
        if "def execute" in new_code and "return" in new_code:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_code, encoding='utf-8')
            print(f"✅ Mutação aplicada com sucesso: {target_file}")
        else:
            print(f"❌ Erro: O código gerado não contém a estrutura 'execute'.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Falha: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
