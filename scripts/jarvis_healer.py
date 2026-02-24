# -*- coding: utf-8 -*-
import argparse
import os
import subprocess
import re
from pathlib import Path

def mass_reindent(directory_path):
    """Aplica autopep8 em todos os arquivos .py do diretório para corrigir indentações."""
    print(f"🧬 Iniciando limpeza em massa no diretório: {directory_path}")
    try:
        # Comando para corrigir identação de todos os arquivos .py recursivamente
        subprocess.run([
            "autopep8", 
            "--in-place", 
            "--recursive",
            "--aggressive",
            "--select=E1,E101,E11,E12", 
            str(directory_path)
        ], check=True)
        
        # Pós-processamento manual para garantir coluna 0 em keywords
        for py_file in Path(directory_path).rglob("*.py"):
            content = py_file.read_text(encoding='utf-8')
            new_content = re.sub(r'^[ \t]+(def |class |import |from )', r'\1', content, flags=re.M)
            if new_content != content:
                py_file.write_text(new_content, encoding='utf-8')
        return True
    except Exception as e:
        print(f"❌ Erro na cura em massa: {e}")
        return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=False)
    parser.add_argument('--log', required=False)
    args = parser.parse_args()
    
    # 1. Alvos específicos baseados no log (Prioridade)
    if args.log and os.path.exists(args.log):
        log_content = Path(args.log).read_text(encoding='utf-8')
        matches = re.findall(r'File "([^"]+\.py)"', log_content)
        for f in set(matches):
            p = Path(f).absolute()
            if p.exists() and ".venv" not in str(p):
                print(f"🩹 Curando alvo específico: {p}")
                # Aplicamos a cura no arquivo específico
                subprocess.run(["autopep8", "--in-place", "--aggressive", str(p)])

    # 2. CURA EM MASSA (O pulo do gato)
    # Vamos varrer as pastas onde o JARVIS costuma ter problemas de indentação
    target_dirs = [
        "app/domain/capabilities",
        "app/core",
        "scripts"
    ]
    
    for d in target_dirs:
        dir_path = Path(os.getcwd()) / d
        if dir_path.exists():
            mass_reindent(dir_path)

if __name__ == "__main__":
    heal()
