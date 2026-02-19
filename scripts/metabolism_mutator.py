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

        # --- PASSO 1: ARQUITETURA ---
        analysis_prompt = f"""
        Missão: {issue_body}
        Contexto do Roadmap: {roadmap_context}
        Decida qual arquivo deve ser criado ou editado.
        DIRETRIZES:
        - Serviços: 'app/application/services/'
        - Infra: 'app/adapters/infrastructure/'
        - Scripts: 'scripts/'
        Retorne um JSON com: "target_file", "action", "reason".
        """

        try:
            resp_analysis = requests.post(self.groq_url, headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": "Arquiteto Senior. JSON puro."}, {"role": "user", "content": analysis_prompt}],
                    "response_format": {"type": "json_object"}
                }, timeout=30)

            if resp_analysis.status_code != 200:
                logger.error(f"Erro API Arquitetura: {resp_analysis.text}")
                return {'success': False}

            analysis_data = json.loads(resp_analysis.json()['choices'][0]['message']['content'])
            target_file = analysis_data['target_file']
            logger.info(f"🎯 Alvo: {target_file}")

            path = self.repo_path / target_file
            path.parent.mkdir(parents=True, exist_ok=True)
            current_code = path.read_text(encoding='utf-8') if path.exists() else "# Novo arquivo JARVIS"

            # --- PASSO 2: ENGENHARIA ---
            mutation_prompt = f"Missão: {issue_body}\nArquivo: {target_file}\nCÓDIGO ATUAL:\n{current_code}\nRetorne JSON com 'code' e 'summary'."

            resp_mutation = requests.post(self.groq_url, headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "Engenheiro Senior. Responda APENAS JSON. Campo 'code' deve ter o arquivo COMPLETO."},
                        {"role": "user", "content": mutation_prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }, timeout=60)

            if resp_mutation.status_code != 200:
                logger.error(f"Erro API Engenharia: {resp_mutation.text}")
                return {'success': False}

            data = resp_mutation.json()
            if 'choices' not in data:
                logger.error("Resposta da API sem 'choices'")
                return {'success': False}

            content = json.loads(data['choices'][0]['message']['content'])
            new_code = content.get('code', "")
            summary = content.get('summary', "")

            if isinstance(summary, list): summary = "\n".join([f"- {item}" for item in summary])

            if len(new_code.strip()) > 20:
                path.write_text(new_code, encoding='utf-8')
                (self.repo_path / "mutation_summary.txt").write_text(str(summary), encoding='utf-8')
                logger.info(f"✅ DNA mutado: {target_file}")
                return {'success': True}

        except Exception as e:
            logger.error(f"❌ Falha crítica: {e}")

        return {'success': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()
    MutabolismMutator().apply_mutation(args.strategy, args.intent, args.impact, args.roadmap_context)
    sys.exit(0)
