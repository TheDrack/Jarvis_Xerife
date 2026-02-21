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
    
    # Remove blocos de código markdown (```json ... ``` ou ``` ... ```)
    clean_text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', raw_response, flags=re.DOTALL)
    clean_text = clean_text.strip()
    
    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        # Se falhar, tenta encontrar algo que pareça um JSON { ... }
        match = re.search(r'(\{.*\})', clean_text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Não foi possível parsear o JSON. Resposta bruta: {raw_response[:100]}...")

def evolve():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()

    core = MetabolismCore()
    issue_body = os.getenv('ISSUE_BODY', 'Nova funcionalidade')

    # --- PASSO 1: ARQUITETURA ---
    system_arch = (
        "Você é o Arquiteto Senior. O repositório segue a Clean Architecture.\n"
        "Regra: Proibido arquivos na raiz. Use caminhos completos.\n"
        "Retorne APENAS JSON puro: {\"target_file\": \"path/to/file.py\", \"reason\": \"motivo\"}"
    )
    user_arch = f"MISSÃO: {issue_body}\nCONTEXTO: {args.roadmap_context}"

    try:
        print(f"🧠 Analisando arquitetura...")
        raw_arch = core.ask_jarvis(system_arch, user_arch)
        arch_decision = clean_json_response(raw_arch)
        
        target_file = arch_decision.get('target_file')

        # Fallback de segurança para caminhos
        if not target_file or "/" not in str(target_file):
            print("⚠️ Caminho inválido detectado. Forçando estrutura padrão.")
            filename = str(target_file).split("/")[-1] if target_file else "new_component.py"
            target_file = f"app/application/services/{filename}"

        path = Path(target_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        current_code = path.read_text(encoding='utf-8') if path.exists() else "# DNA Component - Initialized"

        # --- PASSO 2: ENGENHARIA ---
        system_eng = (
            "Você é o Engenheiro Senior. Implemente o código completo em Python.\n"
            "Não use explicações. Responda APENAS o JSON no formato:\n"
            "{\"code\": \"codigo_aqui\", \"summary\": \"resumo\"}"
        )
        user_eng = f"OBJETIVO: {issue_body}\nARQUIVO: {target_file}\nCÓDIGO ATUAL:\n{current_code}"

        print(f"🧬 Gerando código para: {target_file}")
        raw_mutation = core.ask_jarvis(system_eng, user_eng)
        mutation = clean_json_response(raw_mutation)

        new_code = mutation.get('code', '')
        summary = mutation.get('summary', 'Evolução de componente')

        if len(new_code.strip()) > 20:
            path.write_text(new_code, encoding='utf-8')
            print(f"✅ Evolução aplicada em: {target_file}")
            print(f"📝 Resumo: {summary}")
        else:
            print("❌ Erro: O código gerado é insuficiente ou vazio.")
            print(f"DEBUG: Resposta recebida: {mutation}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Falha crítica no processo: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
