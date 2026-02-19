# -*- coding: utf-8 -*-
import argparse, os, sys, json
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

    # Passo 1: Definir o alvo da mutação
    system_arch = "Você é o Arquiteto Senior do JARVIS. Decida qual arquivo deve ser alterado ou criado para a missão. Responda JSON: {'target_file': 'caminho/do/arquivo.py', 'reason': 'motivo'}."
    user_arch = f"Missão: {issue_body}\nContexto: {args.roadmap_context}"
    
    try:
        arch_decision = core.ask_jarvis(system_arch, user_arch)
        target_file = arch_decision['target_file']
        path = Path(target_file)
        
        path.parent.mkdir(parents=True, exist_ok=True)
        current_code = path.read_text(encoding='utf-8') if path.exists() else "# Novo componente JARVIS"

        # Passo 2: Gerar a mutação
        system_eng = "Você é o Engenheiro Senior do JARVIS. Implemente a evolução solicitada. Responda JSON: {'code': 'arquivo completo', 'summary': 'resumo das mudanças'}."
        user_eng = f"Missão: {issue_body}\nArquivo: {target_file}\nCódigo Atual:\n{current_code}"
        
        print(f"🧬 Evoluindo: {target_file}")
        mutation = core.ask_jarvis(system_eng, user_eng)
        
        new_code = mutation.get('code', '')
        if len(new_code.strip()) > 10:
            path.write_text(new_code, encoding='utf-8')
            Path("mutation_summary.txt").write_text(mutation.get('summary', ''), encoding='utf-8')
            print(f"✅ DNA Evoluído: {target_file}")
        else:
            print("❌ Falha: Código de evolução vazio.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Falha na Evolução: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
