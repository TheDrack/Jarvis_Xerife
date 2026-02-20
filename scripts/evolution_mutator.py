# -*- coding: utf-8 -*-
import argparse
import os
import sys
import json
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

def evolve():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()

    core = MetabolismCore()
    issue_body = os.getenv('ISSUE_BODY', 'Nova funcionalidade')

    # --- PASSO 1: ARQUITETURA (Reforçada) ---
    system_arch = (
        "Você é o Arquiteto Senior do JARVIS. O repositório está desorganizado.\n"
        "É PROIBIDO criar arquivos na raiz. Siga esta estrutura:\n"
        "- Serviços: 'app/application/services/'\n"
        "- Modelos: 'app/domain/models/'\n"
        "Sempre use caminhos longos. Retorne JSON: {\"target_file\": \"app/application/services/nome.py\", \"reason\": \"motivo\"}"
    )
    user_arch = f"MISSÃO: {issue_body}\nCONTEXTO: {args.roadmap_context}"

    try:
        print(f"🧠 Analisando arquitetura...")
        arch_decision = core.ask_jarvis(system_arch, user_arch)
        target_file = arch_decision.get('target_file')

        # Fallback de segurança para caminhos
        if not target_file or "/" not in target_file:
            print("⚠️ Arquiteto tentou usar a raiz. Forçando app/application/services/")
            filename = target_file.split("/")[-1] if target_file else "new_component.py"
            target_file = f"app/application/services/{filename}"

        path = Path(target_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        current_code = path.read_text(encoding='utf-8') if path.exists() else "# DNA Component"

        # --- PASSO 2: ENGENHARIA ---
        system_eng = (
            "Você é o Engenheiro Senior. Implemente o código completo.\n"
            "Retorne APENAS um JSON válido: {\"code\": \"...\", \"summary\": \"...\"}"
        )
        user_eng = f"OBJETIVO: {issue_body}\nARQUIVO: {target_file}\nCÓDIGO ATUAL:\n{current_code}"

        print(f"🧬 Gerando código para: {target_file}")
        mutation = core.ask_jarvis(system_eng, user_eng)

        new_code = mutation.get('code', '')
        if len(new_code.strip()) > 20:
            path.write_text(new_code, encoding='utf-8')
            print(f"✅ Evolução aplicada em: {target_file}")
        else:
            sys.exit(1)

    except Exception as e:
        print(f"❌ Falha: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
