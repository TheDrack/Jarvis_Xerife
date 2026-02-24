# -*- coding: utf-8 -*-
import argparse
import json
import re
import os
from pathlib import Path

def structural_healing(file_path, error_msg):
    """Corrige erros de indentação (unexpected indent)."""
    try:
        content = file_path.read_text(encoding='utf-8')
        # Remove espaços no início da linha 2 se houver IndentationError
        lines = content.splitlines()
        if len(lines) >= 2 and "IndentationError" in error_msg:
            # Tenta limpar a indentação da linha citada ou de todas as defs
            new_content = re.sub(r'^[ \t]+(def|class|import|from)', r'\1', content, flags=re.M)
            if new_content != content:
                file_path.write_text(new_content, encoding='utf-8')
                return True
    except Exception as e:
        print(f"Erro ao processar arquivo: {e}")
    return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    
    with open(args.report, 'r') as f:
        report = json.load(f)

    # O Pytest coloca erros de Indentação/Import na lista de topo 'errors'
    issues = report.get('errors', []) + report.get('tests', [])
    
    for issue in issues:
        if issue.get('outcome') == 'passed': continue
        
        # Em erros de coleção, o caminho está no 'nodeid' ou 'message'
        nodeid = issue.get('nodeid', '')
        error_msg = str(issue.get('longrepr', ''))
        
        # Extrai o caminho do arquivo do erro de coleção
        # Ex: "app/domain/capabilities/cap_053_core.py"
        file_match = re.search(r'([\w/]+\.py)', nodeid + error_msg)
        if file_match:
            path = Path(file_match.group(1))
            if path.exists():
                print(f"🧬 Curando anomalia em: {path}")
                structural_healing(path, error_msg)

if __name__ == "__main__":
    heal()
