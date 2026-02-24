# -*- coding: utf-8 -*-
import argparse
import json
import re
import os
import subprocess
from pathlib import Path

def force_reindent(file_path):
    """Usa autopep8 para corrigir indentações de forma profissional."""
    try:
        print(f"  [🔧] Reindentando arquivo via autopep8: {file_path}")
        # Comando para corrigir apenas indentação e erros de sintaxe básica
        subprocess.run([
            "autopep8", 
            "--in-place", 
            "--select=E1,E101,E11,E12,E122", 
            str(file_path)
        ], check=True)
        
        # Pós-processamento manual para garantir que 'def' e 'import' estejam na coluna 0
        content = file_path.read_text(encoding='utf-8')
        new_content = re.sub(r'^[ \t]+(def |class |import |from )', r'\1', content, flags=re.M)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            
        return True
    except Exception as e:
        print(f"  [❌] Erro ao usar autopep8: {e}")
        return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('--log', required=True)
    args = parser.parse_args()
    
    files_to_fix = set()

    # 1. Busca no Log (IndentationError costuma dar o caminho exato)
    if os.path.exists(args.log):
        log_content = Path(args.log).read_text(encoding='utf-8')
        matches = re.findall(r'File "([^"]+\.py)"', log_content)
        files_to_fix.update(matches)

    # 2. Busca no JSON
    if os.path.exists(args.report):
        try:
            with open(args.report, 'r', encoding='utf-8') as f:
                report = json.load(f)
                all_errors = report.get('errors', []) + report.get('tests', [])
                for item in all_errors:
                    if item.get('outcome') != 'passed':
                        # Tenta achar caminho no nodeid ou na mensagem
                        msg = str(item.get('longrepr', '')) + str(item.get('message', ''))
                        path_match = re.search(r'([\w\-/]+\.py)', msg)
                        if path_match:
                            files_to_fix.add(path_match.group(1))
        except: pass

    for f_str in files_to_fix:
        path = Path(f_str).absolute()
        if not path.exists():
            path = Path(os.getcwd()) / f_str

        if path.exists() and path.is_file() and ".venv" not in str(path):
            print(f"🧬 Iniciando cura profunda: {path}")
            force_reindent(path)

if __name__ == "__main__":
    heal()
