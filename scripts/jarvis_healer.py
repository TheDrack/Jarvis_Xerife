# -*- coding: utf-8 -*-
import argparse
import json
import re
import os
from pathlib import Path

def structural_healing(file_path, error_msg):
    """Remove indentação inesperada em linhas de definição e importação."""
    try:
        if not file_path.exists():
            return False
            
        content = file_path.read_text(encoding='utf-8')
        # Regex para remover espaços ou tabs no início de linhas que começam com palavras-chave
        new_content = re.sub(r'^[ \t]+(from|import|def|class)', r'\1', content, flags=re.M)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            print(f"  [FIXED] Indentação corrigida em: {file_path}")
            return True
    except Exception as e:
        print(f"  [ERROR] Falha ao curar {file_path}: {e}")
    return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    
    if not os.path.exists(args.report):
        print("❌ Relatório não encontrado.")
        return

    with open(args.report, 'r', encoding='utf-8') as f:
        report = json.load(f)

    # Captura issues de execução E de coleção (erros de import/indentação)
    all_issues = report.get('tests', []) + report.get('errors', [])
    
    processed_files = set()

    for issue in all_issues:
        if issue.get('outcome') == 'passed':
            continue
            
        # Tenta extrair o caminho do arquivo do nodeid ou da mensagem de erro
        nodeid = issue.get('nodeid', '')
        longrepr = str(issue.get('longrepr', ''))
        message = str(issue.get('message', ''))
        
        # Procura por padrões de caminho de arquivo .py no erro
        potential_paths = re.findall(r'([\w\-/]+\.py)', nodeid + longrepr + message)
        
        for p in potential_paths:
            file_path = Path(p)
            if file_path.exists() and file_path.is_file() and file_path not in processed_files:
                # Evita mexer em arquivos de biblioteca externa
                if ".venv" in str(file_path) or "site-packages" in str(file_path):
                    continue
                    
                print(f"🧬 Analisando anomalia em: {file_path}")
                structural_healing(file_path, longrepr + message)
                processed_files.add(file_path)

if __name__ == "__main__":
    heal()
