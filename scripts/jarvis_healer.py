# -*- coding: utf-8 -*-
import argparse
import json
import re
import os
from pathlib import Path

def structural_healing(file_path):
    """Remove indentação inesperada."""
    try:
        content = file_path.read_text(encoding='utf-8')
        # Remove qualquer espaço no início de linhas que começam com def/class/import
        new_content = re.sub(r'^[ \t]+(from|import|def|class)', r'\1', content, flags=re.M)
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            print(f"  [FIXED] Indentação corrigida em: {file_path}")
            return True
    except Exception as e:
        print(f"  [ERROR] Falha em {file_path}: {e}")
    return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    
    files_to_fix = set()

    # 1. Tenta pegar do Log do Terminal (Mais confiável em erros de indentação)
    if os.path.exists(args.log):
        log_content = Path(args.log).read_text(encoding='utf-8')
        # Procura por caminhos de arquivos que antecedem o erro de indentação
        matches = re.findall(r'File "([^"]+\.py)"', log_content)
        files_to_fix.update(matches)

    # 2. Tenta pegar do JSON se ele existir e for válido
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
        except:
            pass

    for f_str in files_to_fix:
        path = Path(f_str)
        # Filtra para não mexer em arquivos de biblioteca
        if path.exists() and "site-packages" not in f_str and ".venv" not in f_str:
            print(f"🧬 Curando: {path}")
            structural_healing(path)

if __name__ == "__main__":
    heal()
