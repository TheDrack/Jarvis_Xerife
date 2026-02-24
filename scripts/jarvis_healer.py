# -*- coding: utf-8 -*-
import argparse
import json
import re
import os
from pathlib import Path

def aggressive_structural_healing(file_path):
    """
    Cura incondicional: Corrige indentação e garante 
    que o arquivo não termine em blocos vazios.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # 1. Remove indentação de primeiro nível (Imports, Defs, Classes)
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            # Se a linha começa com palavras core, forçamos o início na coluna 0
            if re.match(r'^[ \t]+(from|import|def|class|if __name__)', line):
                new_lines.append(line.lstrip())
            else:
                new_lines.append(line)
        
        # 2. Garante que se houver um 'def execute', ele tenha ao menos um 'pass' ou lógica
        temp_content = "\n".join(new_lines)
        if "def execute" in temp_content and "pass" not in temp_content and ":" in temp_content:
            temp_content = temp_content.replace("def execute(context=None):", "def execute(context=None):\n    pass")

        # 3. Limpeza de espaços duplos e trailing spaces
        final_content = re.sub(r'[ \t]+$', '', temp_content, flags=re.M)
        
        if final_content != content:
            file_path.write_text(final_content, encoding='utf-8')
            print(f"  [💊 CURADO] Estrutura sanitizada: {file_path}")
            return True
    except Exception as e:
        print(f"  [⚠️ ERRO] Falha crítica ao acessar {file_path}: {e}")
    return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    
    files_to_fix = set()

    # Extração via Log (Onde o erro real aparece)
    if os.path.exists(args.log):
        log_content = Path(args.log).read_text(encoding='utf-8')
        matches = re.findall(r'File "([^"]+\.py)"', log_content)
        files_to_fix.update(matches)

    # Extração via JSON (Para erros de teste)
    if os.path.exists(args.report):
        try:
            with open(args.report, 'r', encoding='utf-8') as f:
                report = json.load(f)
                errors = report.get('errors', []) + report.get('tests', [])
                for issue in errors:
                    if issue.get('outcome') != 'passed':
                        nodeid = issue.get('nodeid', '')
                        file_match = re.search(r'([\w\-/]+\.py)', nodeid)
                        if file_match:
                            files_to_fix.add(file_match.group(1))
        except: pass

    for f_str in files_to_fix:
        # Resolve o caminho absoluto para evitar erros de diretório
        path = Path(f_str).absolute()
        # Se o caminho for relativo ao runner
        if not path.exists():
            path = Path(os.getcwd()) / f_str

        if path.exists() and path.is_file():
            if ".venv" in str(path) or "site-packages" in str(path):
                continue
            print(f"🧬 Iniciando procedimento cirúrgico: {path}")
            aggressive_structural_healing(path)

if __name__ == "__main__":
    heal()
