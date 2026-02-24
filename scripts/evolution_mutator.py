# -*- coding: utf-8 -*-
import argparse
import os
import sys
import json
import re
from pathlib import Path
from app.application.services.metabolism_core import MetabolismCore

def extract_code_manually(text):
    """Tenta extrair o código mesmo se a IA falhar no JSON puro."""
    code_match = re.search(r'```python\n(.*?)\n```', text, re.DOTALL)
    if not code_match:
        code_match = re.search(r'```\n(.*?)\n```', text, re.DOTALL)
    return code_match.group(1) if code_match else text

def clean_json_response(raw_response):
    if isinstance(raw_response, dict): return raw_response
    try:
        clean_text = re.sub(r'```(?:json)?\n?(.*?)\n?```', r'\1', raw_response, flags=re.DOTALL).strip()
        return json.loads(clean_text)
    except:
        match = re.search(r'(\{.*\})', raw_response, re.DOTALL)
        if match:
            try: return json.loads(match.group(1))
            except: pass
        return {"code": extract_code_manually(raw_response), "summary": "Fallback extraction"}

def get_entry_from_crystal(cap_id: str, crystal_path="data/master_crystal.json"):
    path = Path(crystal_path)
    if not path.exists(): return None
    with open(path, 'r', encoding='utf-8') as f:
        crystal = json.load(f)
    for entry in crystal.get("registry", []):
        if entry["id"] == cap_id: return entry
    return None

def update_capability_status(cap_id: str, status="complete", cap_path="data/capabilities.json"):
    """
    Sincroniza o status no arquivo base para que o Crystallizer Engine 
    possa computar a métrica correta no Master Crystal.
    """
    path = Path(cap_path)
    if not path.exists():
        print(f"⚠️ Alerta: {cap_path} não encontrado para atualização de status.")
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        updated = False
        for cap in data.get('capabilities', []):
            if cap['id'] == cap_id:
                cap['status'] = status
                updated = True
                break

        if updated:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"💾 DNA Sincronizado: {cap_id} marcado como {status} em {cap_path}")
            return True
    except Exception as e:
        print(f"❌ Erro ao atualizar status no DNA: {e}")
    return False

def evolve():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()

    issue_body = os.getenv('ISSUE_BODY', '')
    cap_id = None

    match = re.search(r'(CAP-\d+)', issue_body)
    if match:
        cap_id = match.group(1)
    elif args.roadmap_context:
        match = re.search(r'(CAP-\d+)', args.roadmap_context)
        if match:
            cap_id = match.group(1)

    if not cap_id:
        print("❌ Erro: CAP_ID não encontrado.")
        sys.exit(1)

    core = MetabolismCore()
    entry = get_entry_from_crystal(cap_id)
    if not entry:
        print(f"❌ Erro: {cap_id} não registrado no master_crystal.json")
        sys.exit(1)

    target_file = Path(entry["genealogy"]["target_file"])

    system_prompt = (
        f"Você é o motor de evolução do JARVIS. Implemente a lógica da {cap_id}.\n"
        "RESPONDA APENAS O CÓDIGO DENTRO DE UM JSON.\n"
        "O código deve ter: def execute(context=None):"
    )
    user_prompt = f"CONTEXTO: {args.roadmap_context}\nARQUIVO: {target_file}"

    try:
        print(f"🧬 Evoluindo {cap_id} em {target_file}...")
        response = core.ask_jarvis(system_prompt, user_prompt)
        mutation = clean_json_response(response)
        new_code = mutation.get('code', '')

        if "def execute" not in new_code:
            new_code = extract_code_manually(response)

        if "def execute" in new_code:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(new_code, encoding='utf-8')
            print(f"✅ Sucesso: {target_file} mutado.")

            # --- NOVA LÓGICA DE SINCRONIZAÇÃO ---
            # Se o arquivo foi mutado com sucesso, marcamos como complete
            update_capability_status(cap_id)
            # ------------------------------------
        else:
            print("❌ Falha crítica: Estrutura 'execute' não encontrada.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Erro na mutação: {e}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
