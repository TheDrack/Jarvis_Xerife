# -*- coding: utf-8 -*-
import os
import sys
import json
import re
import datetime
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MetabolismMutator:
    def __init__(self, repo_path: str = None):
        self.repo_path = Path(repo_path) if repo_path else Path(os.getcwd())
        self.mutation_log = []
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"

    def _engineering_brainstorm(self, issue_body: str, roadmap_context: str) -> Dict[str, Any]:
        """IA decide o que mudar usando o modelo mais recente e resiliente"""
        import time
        logger.info("🧠 Brainstorming de Evolução (Modelo: Llama-3.3-70b-Versatile)...")
        api_key = os.getenv('GROQ_API_KEY')

        prompt = f"""
        Você é o Arquiteto de Evolução do JARVIS. 
        CONTEXTO DO ROADMAP: {roadmap_context}
        MISSÃO ATUAL: {issue_body}
        
        REGRAS:
        1. Foque na estabilização do Q1 2026.
        2. Mantenha compatibilidade com testes (Exit Code 124 para timeout é OBRIGATÓRIO).
        
        Responda APENAS um JSON:
        {{
            "mission_type": "functional_upgrade",
            "target_files": ["app/application/services/task_runner.py"],
            "required_actions": ["Lista de melhorias técnicas"],
            "can_auto_implement": true
        }}
        """

        for attempt in range(3):
            try:
                import requests
                response = requests.post(
                    self.groq_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"}
                    },
                    timeout=30
                )
                data = response.json()

                if 'choices' not in data:
                    logger.error(f"❌ Erro na API Groq: {data}")
                    time.sleep(10)
                    continue

                content = json.loads(data['choices'][0]['message']['content'])
                usage = data.get('usage', {})
                content['usage'] = {
                    'total_tokens': usage.get('total_tokens', 0),
                    'cost': (usage.get('total_tokens', 0) / 1_000_000) * 0.70
                }
                return content
            except Exception as e:
                logger.error(f"❌ Erro na tentativa {attempt + 1}: {e}")
                time.sleep(5)

        return {'can_auto_implement': False}

    def _validate_integrity(self, old_code: str, new_code: str) -> bool:
        """Verifica se a mutação não removeu métodos essenciais (Anticorpos)"""
        old_methods = re.findall(r'def\s+(\w+)\s*\(', old_code)
        new_methods = re.findall(r'def\s+(\w+)\s*\(', new_code)
        
        # Se perdermos métodos, a IA provavelmente truncou ou "limpou" demais
        missing = set(old_methods) - set(new_methods)
        if missing:
            logger.warning(f"⚠️ Integridade violada! Métodos ausentes: {missing}")
            return False
        return True

    def _reactive_mutation(self, mission_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica a mutação com defesa contra truncamento e perda de funções"""
        logger.info("⚡ Executando Mutação Autônoma...")
        files_changed = []
        api_key = os.getenv('GROQ_API_KEY')

        for file_path_str in mission_analysis.get('target_files', []):
            file_path = self.repo_path / file_path_str
            if not file_path.exists(): continue

            current_code = file_path.read_text(encoding='utf-8')
            prompt = f"Melhore este código seguindo o Roadmap. AÇÕES: {mission_analysis.get('required_actions')}\n\nCÓDIGO:\n{current_code}"

            try:
                import requests
                resp = requests.post(
                    self.groq_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": """Você é o Arquiteto JARVIS. 
REGRAS CRÍTICAS:
1. Retorne o código COMPLETO.
2. MANTENHA todos os métodos de Budget e Timeout (Exit Code 124).
3. Responda APENAS com código Python puro, sem Markdown."""},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1
                    }
                )

                new_code = resp.json()['choices'][0]['message']['content']
                new_code = re.sub(r'```(?:python)?', '', new_code).strip()

                # Fechamento de segurança para evitar SyntaxError por truncamento
                if new_code.count('"""') % 2 != 0: new_code += '\n    """'
                if new_code.count('(') > new_code.count(')'): new_code += ')' * (new_code.count('(') - new_code.count(')'))

                # VALIDAÇÃO DUPLA: Sintaxe + Integridade Funcional
                try:
                    compile(new_code, file_path_str, 'exec')
                    if self._validate_integrity(current_code, new_code):
                        file_path.write_text(new_code, encoding='utf-8')
                        files_changed.append(file_path_str)
                        logger.info(f"✅ DNA validado: {file_path_str}")
                    else:
                        logger.error(f"❌ Mutação REJEITADA por perda de métodos em {file_path_str}")
                except SyntaxError as se:
                    logger.error(f"⚠️ Erro de Sintaxe na mutação: {se}")

            except Exception as e:
                logger.error(f"❌ Erro crítico em {file_path_str}: {e}")

        return {'success': len(files_changed) > 0, 'mutation_applied': len(files_changed) > 0, 'files_changed': files_changed}

    # ... (Mantenha os métodos _update_evolution_dashboard, apply_mutation, etc., como no seu original)

    def apply_mutation(self, strategy: str, intent: str, impact: str, roadmap_context: str = None) -> Dict[str, Any]:
        issue_body = os.getenv('ISSUE_BODY', 'Evolução Contínua')
        analysis = self._engineering_brainstorm(issue_body, roadmap_context or "")
        result = self._reactive_mutation(analysis) if analysis.get('can_auto_implement') else self._create_manual_marker(intent, impact, issue_body)
        
        if result.get('success') and analysis.get('usage'):
            self._update_evolution_dashboard(analysis.get('mission_type', intent), 
                                           analysis['usage']['total_tokens'], analysis['usage']['cost'])
        
        self._save_mutation_log(strategy, intent, impact, result)
        self._export_to_github_actions(result)
        return result

    def _create_manual_marker(self, intent: str, impact: str, issue_body: str) -> Dict[str, Any]:
        marker_dir = self.repo_path / ".github" / "metabolism_markers"
        marker_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        marker_file = marker_dir / f"mutation_{timestamp}.md"
        marker_file.write_text(f"# Marcador Manual\n{issue_body}")
        return {'success': True, 'files_changed': [str(marker_file)]}

    def _save_mutation_log(self, strategy, intent, impact, result):
        log_dir = self.repo_path / ".github" / "metabolism_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(log_dir / f"mutation_{timestamp}.json", 'w') as f:
            json.dump({'strategy': strategy, 'result': result}, f)

    def _export_to_github_actions(self, result):
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
                f.write(f"mutation_applied={str(result.get('mutation_applied', False)).lower()}\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()

    mutator = MetabolismMutator()
    res = mutator.apply_mutation(args.strategy, args.intent, args.impact, args.roadmap_context)
    sys.exit(0 if res.get('success') else 1)
