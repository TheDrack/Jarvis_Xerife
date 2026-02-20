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

    # --- PASSO 1: ARQUITETURA ---
    system_arch = (
        "Você é o Arquiteto Senior do JARVIS. Sua missão é decidir o local EXATO do arquivo.\n"
        "REGRAS DE ORGANIZAÇÃO:\n"
        "1. Serviços e lógica: 'app/application/services/'\n"
        "2. Modelos de dados: 'app/domain/models/'\n"
        "3. Scripts utilitários: 'scripts/'\n"
        "4. Configurações: 'config/'\n"
        "Retorne APENAS o JSON: {\"target_file\": \"caminho/completo/nome_do_arquivo.py\", \"reason\": \"justificativa\"}"
    )

    user_arch = f"MISSÃO: {issue_body}\nCONTEXTO TÉCNICO: {args.roadmap_context}"

    try:
        print(f"🧠 JARVIS analisando arquitetura para: {issue_body}...")
        arch_decision = core.ask_jarvis(system_arch, user_arch)
        
        print(f"DEBUG: Resposta do Arquiteto: {arch_decision}")

        target_file = arch_decision.get('target_file')

        if not target_file:
            print("⚠️ Chave 'target_file' ausente. Iniciando varredura de recuperação...")
            for value in arch_decision.values():
                if isinstance(value, str) and value.endswith('.py'):
                    target_file = value
                    print(f"✅ Alvo recuperado: {target_file}")
                    break

        if not target_file:
            raise ValueError(f"O Arquiteto não definiu um alvo válido. Resposta: {arch_decision}")

        path = Path(target_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        current_code = path.read_text(encoding='utf-8') if path.exists() else "# Novo componente JARVIS"

        # --- PASSO 2: ENGENHARIA ---
        system_eng = (
            "Você é o Engenheiro Senior do JARVIS. Implemente a evolução técnica.\n"
            "Retorne APENAS um JSON válido. O campo 'code' deve conter o código completo.\n"
            "Use \\n para quebras de linha e \\\" para aspas internas."
        )
        
        # CORREÇÃO: Usando aspas triplas para evitar o erro de string não terminada
        user_eng = f"""OBJETIVO: {issue_body}
ARQUIVO: {target_file}
CÓDIGO ATUAL:
{current_code}"""

        print(f"🧬 Gerando mutação de DNA em: {target_file}")
        mutation = core.ask_jarvis(system_eng, user_eng)

        new_code = mutation.get('code', '')
        summary = mutation.get('summary', 'Evolução aplicada.')

        if len(new_code.strip()) > 20:
            path.write_text(new_code, encoding='utf-8')
            Path("mutation_summary.txt").write_text(str(summary), encoding='utf-8')
            print(f"✅ Evolução Concluída: {target_file}")
        else:
            print("❌ Erro: Código gerado insuficiente.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Falha Crítica no Ciclo de Evolução: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
