# -*- coding: utf-8 -*-
import argparse
import os
import subprocess
import re
import requests
from pathlib import Path

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def call_groq_healer(file_content, error_log):
    """Protocolo de Cura Lógica via Groq API."""
    if not GROQ_API_KEY:
        return None

    prompt = f"""
    SISTEMA: JARVIS AUTO-CURA V3.
    TAREFA: Corrija o erro no código Python baseado no log.
    REGRAS: Retorne APENAS o código completo corrigido. Sem markdown, sem explicações.
    
    LOG: {error_log[-2000:]}
    CÓDIGO: {file_content}
    """

    try:
        response = requests.post(GROQ_URL, 
                                 headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                                 json={
                                     "model": "llama-3.3-70b-versatile",
                                     "messages": [{"role": "user", "content": prompt}],
                                     "temperature": 0.1
                                 }, timeout=30)
        return response.json()['choices'][0]['message']['content'].strip()
    except:
        return None

def mass_reindent(directory_path):
    """Cura estrutural via autopep8."""
    print(f"🧬 Reindentando: {directory_path}")
    subprocess.run([
        "autopep8", "--in-place", "--recursive", "--aggressive",
        "--select=E1,E101,E11,E12", str(directory_path)
    ], check=False)

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=False)
    parser.add_argument('--log', required=False)
    args = parser.parse_args()

    error_context = ""
    target_files = set()

    if args.log and os.path.exists(args.log):
        error_context = Path(args.log).read_text(encoding='utf-8')
        matches = re.findall(r'File "([^"]+\.py)"', error_context)
        target_files.update([Path(f).absolute() for f in matches if ".venv" not in f])

    for file_path in target_files:
        if file_path.exists():
            print(f"🩹 Corrigindo lógica: {file_path.name}")
            original = file_path.read_text(encoding='utf-8')
            fixed = call_groq_healer(original, error_context)
            if fixed and ("def " in fixed or "class " in fixed or "import " in fixed):
                file_path.write_text(fixed, encoding='utf-8')

    target_dirs = ["app/domain/capabilities", "app/core", "scripts"]
    for d in target_dirs:
        dir_path = Path(os.getcwd()) / d
        if dir_path.exists():
            mass_reindent(dir_path)

if __name__ == "__main__":
    heal()
