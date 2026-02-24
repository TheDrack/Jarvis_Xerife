# -*- coding: utf-8 -*-
import argparse, json, sys, os, re
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

def structural_healing(file_path, error_msg):
    """Cura rápida para erros de caminhos e imports sem usar LLM."""
    content = file_path.read_text(encoding='utf-8')
    new_content = content
    
    # Se o erro for ModuleNotFoundError, tentamos corrigir o padrão src -> app
    if "ModuleNotFoundError" in error_msg or "ImportError" in error_msg:
        new_content = re.sub(r'from src\.', 'from app.', new_content)
        new_content = re.sub(r'import system_state', 'from app.domain.models import system_state', new_content)
        # Adicione aqui outros padrões comuns que você encontrar
    
    if new_content != content:
        file_path.write_text(new_content, encoding='utf-8')
        return True
    return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()

    core = MetabolismCore()
    report_path = Path(args.report)

    if not report_path.exists():
        print(f"⚠️ Aviso: Relatório {args.report} não encontrado. Abortando cura.")
        return 

    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        failed_tests = [t for t in report.get('tests', []) if t.get('outcome') == 'failed']

        if not failed_tests:
            print("✅ Nada para curar. Todos os testes passaram.")
            return

        for error_detail in failed_tests:
            nodeid = error_detail.get('nodeid', '')
            file_to_fix = nodeid.split('::')[0] if '::' in nodeid else nodeid
            # O longrepr pode ser uma string ou um dict dependendo do pytest-json-report
            long_repr = error_detail.get('call', {}).get('longrepr', '')
            error_msg = str(long_repr)
            
            path = Path(file_to_fix)
            if not path.exists(): continue

            print(f"🧬 Analisando {file_to_fix}...")

            # Tenta cura estrutural primeiro (Rápida e Barata)
            if structural_healing(path, error_msg):
                print(f"🩹 Cura estrutural (imports) aplicada em {file_to_fix}")
                continue

            # Se a cura estrutural não bastar, usa o MetabolismCore (LLM)
            current_code = path.read_text(encoding='utf-8')
            system_p = "Você é o Engenheiro de Auto-Cura do JARVIS. Responda APENAS JSON: {'code': str, 'explanation': str}"
            user_p = f"ARQUIVO: {file_to_fix}\nERRO:\n{error_msg}\nCÓDIGO:\n{current_code}"

            print(f"🧠 Consultando MetabolismCore para {file_to_fix}...")
            solution = core.ask_jarvis(system_p, user_p)
            new_code = solution.get('code', '')

            if new_code and len(new_code.strip()) > 10:
                path.write_text(new_code, encoding='utf-8')
                print(f"✅ Sucesso: {file_to_fix} corrigido. {solution.get('explanation')}")

    except Exception as e:
        print(f"❌ Erro no Healer: {str(e)}")

if __name__ == "__main__":
    heal()
