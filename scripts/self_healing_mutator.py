# -*- coding: utf-8 -*-
import argparse, json, sys, os
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

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
            return

        error_detail = failed_tests[0]
        nodeid = error_detail.get('nodeid', '')
        file_to_fix = nodeid.split('::')[0] if '::' in nodeid else nodeid
        error_msg = error_detail.get('call', {}).get('longrepr', 'Erro desconhecido.')

        path = Path(file_to_fix)
        if not path.exists():
            return

        current_code = path.read_text(encoding='utf-8')
        system_p = "Você é o Engenheiro de Auto-Cura do JARVIS. Responda APENAS JSON: {'code': str, 'explanation': str}"
        user_p = f"ARQUIVO: {file_to_fix}\nERRO:\n{error_msg}\nCÓDIGO:\n{current_code}"

        solution = core.ask_jarvis(system_p, user_p)
        new_code = solution.get('code', '')
        
        if len(new_code.strip()) > 10:
            path.write_text(new_code, encoding='utf-8')
            print(f"✅ Sucesso: {file_to_fix} corrigido. {solution.get('explanation')}")

    except Exception as e:
        print(f"❌ Erro no Mutator: {str(e)}")

if __name__ == "__main__":
    heal()
