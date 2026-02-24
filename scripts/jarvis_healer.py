# -*- coding: utf-8 -*-
import argparse
import json
import re
from pathlib import Path

def structural_healing(file_path, error_msg):
    """Corrige erros de indentação e estrutura básica."""
    try:
        content = file_path.read_text(encoding='utf-8')
        new_content = content
        
        # Correção agressiva de Indentação para imports e definições
        if "IndentationError" in error_msg:
            # Remove espaços/tabs no início de linhas que começam com palavras-chave core
            new_content = re.sub(r'^[ \t]+(from|import|def|class)', r'\1', content, flags=re.M)
        
        if new_content != content:
            file_path.write_text(new_content, encoding='utf-8')
            return True
    except Exception as e:
        print(f"  [!] Erro ao acessar {file_path}: {e}")
    return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    
    report_path = Path(args.report)
    if not report_path.exists():
        print("❌ Relatório não encontrado.")
        return

    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    # Coleta issues de execução (tests) e de coleção (errors)
    all_issues = report.get('tests', []) + report.get('errors', [])
    
    processed_files = set()

    for issue in all_issues:
        if issue.get('outcome') == 'passed':
            continue
        
        # Extrai o caminho do arquivo do nodeid
        nodeid = issue.get('nodeid', '')
        file_str = nodeid.split('::')[0] if '::' in nodeid else nodeid
        file_path = Path(file_str)
        
        # Pega a mensagem de erro (longrepr ou mensagem de erro de coleção)
        error_msg = str(issue.get('longrepr', ''))
        
        if file_path.exists() and file_path.is_file() and file_path not in processed_files:
            print(f"🧬 Analisando: {file_path}")
            if structural_healing(file_path, error_msg):
                print(f"✅ Patch estrutural aplicado em {file_path}")
                processed_files.add(file_path)
            else:
                print(f"⚠️ Não foi possível aplicar patch automático em {file_path}")

if __name__ == "__main__":
    heal()
