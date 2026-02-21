# -*- coding: utf-8 -*-
import argparse
import os
import sys
import json
import re
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

def clean_json_response(raw_response):
    """ Remove blocos de markdown e limpa a string para conversão JSON. """
    if isinstance(raw_response, dict):
        return raw_response
    clean_text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', raw_response, flags=re.DOTALL)
    clean_text = clean_text.strip()
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        match = re.search(r'(\{.*\})', clean_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Não foi possível parsear o JSON: {raw_response[:100]}...")

def get_target_from_crystal(cap_id: str, crystal_path="data/master_crystal.json"):
    """ Consulta o DNA do sistema para saber onde a peça deve ser montada. """
    path = Path(crystal_path)
    if not path.exists():
        return None
    
    crystal = json.loads(path.read_text(encoding='utf-8'))
    for entry in crystal.get("registry", []):
        if entry["id"] == cap_id:
            return entry["genealogy"]["target_file"]
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
    
    # Extrair ID da missão (ex: CAP-024)
    match = re.search(r'(CAP-\d+)', issue_body)
    if not match:
        print("❌ Erro: ID da capability não encontrado no ISSUE_BODY.")
        sys.exit(1)
    
    cap_id = match.group(1)
    
    # --- PASSO 1: LOCALIZAÇÃO (Via Crystallizer DNA) ---
    print(f"🔍 Consultando DNA para missão: {cap_id}")
    target_file = get_target_from_crystal(cap_id)
    
    if not target_file:
        print(f"⚠️ {cap_id} não encontrado no Master Crystal. Abortando para evitar poluição.")
        sys.exit(1)

    path = Path(target_file)
    # O Crystallizer já criou o arquivo, então lemos o placeholder
    current_code = path.read_text(encoding='utf-8') if path.exists() else "# Placeholder"

    # --- PASSO 2: ENGENHARIA (Injeção de Lógica) ---
    system_eng = (
        "Você é o Engenheiro Senior do JARVIS. Sua tarefa é implementar a lógica completa.\n"
        f"O arquivo está localizado em: {target_file}\n"
        "Não use explicações. Responda APENAS o JSON no formato:\n"
        "{\"code\": \"codigo_python_completo\", \"summary\": \"resumo\"}"
    )
    user_eng = (
        f"OBJETIVO: {issue_body}\n"
        f"CONTEXTO DO ROADMAP: {args.roadmap_context}\n"
        f"ESTRUTURA ATUAL:\n{current_code}"
    )

    try:
        print(f"🧬 Mutando código em: {target_file}")
        raw_mutation = core.ask_jarvis(system_eng, user_eng)
        mutation = clean_json_response(raw_mutation)

        new_code = mutation.get('code', '')
        summary = mutation.get('summary', 'Evolução JARVIS')

        if len(new_code.strip()) > 20:
            path.write_text(new_code, encoding='utf-8')
            print(f"✅ Mutação aplicada com sucesso em: {target_file}")
            print(f"📝 Resumo: {summary}")
        else:
            print("❌ Erro: Código gerado insuficiente.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Falha crítica na mutação: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
