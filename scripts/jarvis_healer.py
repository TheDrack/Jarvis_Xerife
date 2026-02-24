# -*- coding: utf-8 -*-
import argparse
import os
import subprocess
import re
import json
import requests
from pathlib import Path

# Configurações da Groq (Certifique-se que GROQ_API_KEY esteja no ENV do Github Actions)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def call_groq_healer(file_content, error_log):
    """Envia o código e o erro para a Groq sugerir a correção técnica."""
    if not GROQ_API_KEY:
        print("⚠️ GROQ_API_KEY não encontrada. Pulando correção lógica.")
        return None

    prompt = f"""
    SISTEMA: Você é o JARVIS: PROTOCOLO DE AUTO-CURA.
    TAREFA: Corrija o erro no código Python abaixo baseado no log de erro fornecido.
    REGRAS: 
    1. Retorne APENAS o código corrigido completo.
    2. Não explique nada. Sem markdown de bloco de código (```python).
    3. Mantenha a lógica original, corrija apenas o erro reportado.

    LOG DE ERRO:
    {error_log}

    CÓDIGO ORIGINAL:
    {file_content}
    """
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1
    }

    try:
        response = requests.post(GROQ_URL, headers=headers, json=data, timeout=30)
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"❌ Erro na comunicação com Groq: {e}")
        return None

def mass_reindent(directory_path):
    """Aplica autopep8 e limpeza de keywords em massa."""
    print(f"🧹 Limpeza em massa: {directory_path}")
    try:
        subprocess.run([
            "autopep8", "--in-place", "--recursive", "--aggressive",
            "--select=E1,E101,E11,E12", str(directory_path)
        ], check=True)
        return True
    except Exception as e:
        print(f"❌ Erro na reindentação: {e}")
        return False

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=False)
    parser.add_argument('--log', required=False)
    args = parser.parse_args()

    error_context = ""
    target_files = set()

    # 1. Analisar Log para identificar culpados e contexto
    if args.log and os.path.exists(args.log):
        error_context = Path(args.log).read_text(encoding='utf-8')
        # Captura arquivos que aparecem no Traceback
        matches = re.findall(r'File "([^"]+\.py)"', error_context)
        target_files.update([Path(f).absolute() for f in matches if ".venv" not in f])

    # 2. Tentativa de Cura Lógica com Groq
    for file_path in target_files:
        if file_path.exists():
            print(f"🧬 Aplicando Auto-Cura Lógica: {file_path.name}")
            original_code = file_path.read_text(encoding='utf-8')
            
            # Chama a IA para consertar o erro do log
            fixed_code = call_groq_healer(original_code, error_context)
            
            if fixed_code and "def " in fixed_code: # Validação simples se retornou código
                file_path.write_text(fixed_code, encoding='utf-8')
                print(f"✅ Arquivo {file_path.name} reconstruído pela IA.")

    # 3. Cura Estrutural (Indentação) em massa como fallback/segurança
    target_dirs = ["app/domain/capabilities", "app/core", "scripts"]
    for d in target_dirs:
        dir_path = Path(os.getcwd()) / d
        if dir_path.exists():
            mass_reindent(dir_path)

if __name__ == "__main__":
    heal()
