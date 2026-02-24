# -*- coding: utf-8 -*-
import argparse, json, sys, os, re
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

def structural_healing(file_path, error_msg):
    content = file_path.read_text(encoding='utf-8')
    new_content = content
    
    # Corrige Indentação (Remove espaços extras antes de def/class)
    if "IndentationError" in error_msg:
        print(f"  [!] Corrigindo indentação em {file_path}")
        new_content = re.sub(r'^[ \t]+(def|class)', r'\1', new_content, flags=re.M)
        # Se for na linha 2 especificamente como o log mostrou:
        lines = new_content.splitlines()
        if len(lines) > 1 and lines[1].startswith(' '):
            lines[1] = lines[1].lstrip()
        new_content = '\n'.join(lines)

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
    if not report_path.exists(): return 

    try:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        # Pega erros de TESTE e erros de COLEÇÃO (import/syntax)
        failed_items = report.get('tests', []) + report.get('errors', [])
        
        for item in failed_items:
            if item.get('outcome') == 'passed': continue
            
            nodeid = item.get('nodeid', '')
            file_to_fix = nodeid.split('::')[0] if '::' in nodeid else nodeid
            # Pega a mensagem de erro onde quer que ela esteja no JSON
            error_msg = str(item.get('longrepr', '')) or str(item.get('call', {}).get('longrepr', ''))
            
            path = Path(file_to_fix)
            if not path.exists():
                # Se o arquivo não existe, o problema pode ser o nome do módulo no import
                print(f"  [?] Arquivo {file_to_fix} não existe. Verificando erro de módulo...")
                continue

            print(f"🧬 Tentando curar: {file_to_fix}")
            if structural_healing(path, error_msg):
                print(f"✅ Patch aplicado.")
            else:
                # Se não for erro simples, vai para o LLM
                current_code = path.read_text(encoding='utf-8')
                sol = core.ask_jarvis("Corrija o código Python. Responda APENAS JSON: {'code': str, 'explanation': str}", 
                                     f"ERRO: {error_msg}\nCÓDIGO:\n{current_code}")
                if sol.get('code'):
                    path.write_text(sol['code'], encoding='utf-8')
                    print(f"🧠 Corrigido via LLM: {sol.get('explanation')}")

    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    heal()
