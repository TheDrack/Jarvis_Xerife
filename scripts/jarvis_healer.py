# -*- coding: utf-8 -*-
import argparse
import json
import re
from pathlib import Path

def structural_healing(file_path, error_msg):
    """Corrige IndentationError e erros básicos de estrutura."""
    try:
        content = file_path.read_text(encoding='utf-8')
        new_content = content
        
        # Se houver erro de indentação, remove espaços/tabs antes de def, class, import
        if "IndentationError" in error_msg:
            print(f"  [!] Aplicando correção de indentação em {file_path}")
            new_content = re.sub(r'^[ \t]+(from|import|def|class)', r'\1', content, flags=re.M)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            return True
    except Exception as e:
        print(f"  [!] Erro ao processar arquivo {file_path}: {e}")
    return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    
    report_path = Path(args.report)
    if not report_path.exists():
        return

    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    # Coleta issues de execução e de coleção (onde moram os erros de indentação)
    issues = report.get('errors', []) + report.get('tests', [])
    
    for issue in issues:
        if issue.get('outcome') == 'passed':
            continue
        
        nodeid = issue.get('nodeid', '')
        error_msg = str(issue.get('longrepr', ''))
        
        # Tenta extrair o caminho do arquivo do nodeid ou da mensagem
        file_match = re.search(r'([\w\-/]+\.py)', nodeid + error_msg)
        if file_match:
            path = Path(file_match.group(1))
            if path.exists() and path.is_file():
                print(f"🧬 Iniciando cura em: {path}")
                structural_healing(path, error_msg)

if __name__ == "__main__":
    heal()
