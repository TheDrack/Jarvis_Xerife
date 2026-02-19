# -*- coding: utf-8 -*-
import os, sys, json, re, argparse, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("Mutator")

class MetabolismMutator:
    def __init__(self, repo_path=None):
        self.repo_path = Path(repo_path) if repo_path else Path(os.getcwd())
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"

    def apply_mutation(self, strategy, intent, impact, roadmap_context):
        issue_body = os.getenv('ISSUE_BODY', 'Evolução')
        api_key = os.getenv('GROQ_API_KEY')

        try:
            import requests
        except ImportError:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
            import requests

        # --- PASSO 1: DECIDIR O ALVO (ARQUITETURA) ---
        analysis_prompt = f"""
        Missão: {issue_body}
        Contexto do Roadmap: {roadmap_context}
        Como um Arquiteto de Software, decida qual arquivo deve ser criado ou editado para realizar esta missão.
        Retorne um JSON com:
        "target_file": "caminho/relativo/do/arquivo.py",
        "action": "create" ou "edit",
        "reason": "breve explicação"
        """

        try:
            resp_analysis = requests.post(self.groq_url, headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Você é um Arquiteto de Software. Responda apenas JSON puro."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    "response_format": {"type": "json_object"}
                }, timeout=30)
            
            analysis_data = json.loads(resp_analysis.json()['choices'][0]['message']['content'])
            target_file = analysis_data['target_file']
            logger.info(f"🎯 Alvo identificado: {target_file} ({analysis_data['action']})")
            
            path = self.repo_path / target_file
            path.parent.mkdir(parents=True, exist_ok=True) # Garante que a pasta exista

            current_code = ""
            if path.exists():
                current_code = path.read_text(encoding='utf-8')
            else:
                current_code = "# Novo arquivo criado pelo JARVIS Auto-Evolution"

            # --- PASSO 2: EXECUTAR A MUTAÇÃO (ENGENHARIA) ---
            mutation_prompt = f"""
            Missão: {issue_body}
            Arquivo alvo: {target_file}
            
            CÓDIGO ATUAL:
            {current_code}
            
            Instrução: Implemente as mudanças necessárias para cumprir a missão. 
            Retorne um JSON com:
            'code': (string com o código COMPLETO do arquivo resultante)
            'summary': (string markdown descrevendo o que foi feito)
            """

            resp_mutation = requests.post(self.groq_url, headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Você é um Engenheiro Senior. Responda APENAS com JSON puro. Sempre retorne o código completo do arquivo no campo 'code'."},
                        {"role": "user", "content": mutation_prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }, timeout=60)

            data = resp_mutation.json()
            content_raw = data['choices'][0]['message']['content']
            content = json.loads(content_raw)

            new_code = content.get('code', "")
            summary = content.get('summary', "")

            if isinstance(summary, list):
                summary = "\n".join([f"- {item}" for item in summary])

            # Validação básica: Não salvar se o código vier vazio
            if len(new_code.strip()) > 10:
                path.write_text(new_code, encoding='utf-8')
                (self.repo_path / "mutation_summary.txt").write_text(str(summary), encoding='utf-8')
                logger.info(f"✅ DNA mutado em {target_file}")
                return {'success': True}
            
        except Exception as e:
            logger.error(f"❌ Falha na mutação dinâmica: {e}")
        
        return {'success': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()

    mutator = MetabolismMutator()
    mutator.apply_mutation(args.strategy, args.intent, args.impact, args.roadmap_context)
    sys.exit(0)
