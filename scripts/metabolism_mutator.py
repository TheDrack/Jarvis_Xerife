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

    def _engineering_brainstorm(self, issue_body: str, roadmap_context: str) -> Dict[str, Any]:
        """IA decide o que e onde mudar sem vício em logs"""
        logger.info("🧠 Brainstorming de Evolução...")
        api_key = os.getenv('GROQ_API_KEY')
        
        prompt = f"""
        Você é o Motor de Evolução do JARVIS. 
        CONTEXTO: {roadmap_context}
        MISSÃO: {issue_body}

        TAREFA:
        1. Identifique o arquivo .py mais relevante para esta missão em 'app/'.
        2. Planeje uma mudança funcional real (não apenas logs).
        3. Se a missão for sobre 'logs estruturados', mude como os dados são passados nos arquivos de serviço.
        
        Responda APENAS um JSON:
        {{
            "mission_type": "functional_upgrade",
            "target_files": ["app/application/services/task_runner.py"],
            "required_actions": ["Implementar passagem de mission_id e device_id no construtor e logs"],
            "can_auto_implement": true
        }}
        """

        try:
            import requests
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "llama3-70b-8192", # Modelo estável
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"}
                }
            )
            data = response.json()
            content = json.loads(data['choices'][0]['message']['content'])
            
            # Telemetria para o Dashboard
            usage = data.get('usage', {})
            content['usage'] = {
                'total_tokens': usage.get('total_tokens', 0),
                'cost': (usage.get('total_tokens', 0) / 1_000_000) * 0.70
            }
            return content
        except Exception as e:
            logger.error(f"❌ Falha: {e}")
            return {'can_auto_implement': False}


    def _update_evolution_dashboard(self, mission_name: str, tokens: int, cost: float):
        """Atualiza o Dashboard de Evolução no README.md"""
        logger.info("🏆 Atualizando Dashboard de Evolução...")
        readme_path = self.repo_path / "README.md"
        if not readme_path.exists(): return

        try:
            content = readme_path.read_text(encoding='utf-8')
            intelligence_level = 61.9 
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            new_entry = f"| {date_str} | {mission_name} | {tokens} | ${cost:.6f} | ✅ |\n"

            if "## 🧬 Painel de Evolução JARVIS" in content:
                parts = content.split("## 🧬 Painel de Evolução JARVIS")
                # Mantém o cabeçalho e adiciona a nova linha no topo da tabela
                header_table = "| Data | Missão | Tokens | Custo Est. | Status |\n| :--- | :--- | :--- | :--- | :--- |\n"
                updated_content = parts[0] + "## 🧬 Painel de Evolução JARVIS\n" + \
                                  f"> **Status do DNA:** Estável | **Nível de Inteligência:** {intelligence_level} IQ\n\n" + \
                                  header_table + new_entry + "\n".join(parts[1].split("\n")[6:])
            else:
                dashboard_template = f"\n## 🧬 Painel de Evolução JARVIS\n" \
                                     f"> **Status do DNA:** Estável | **Nível de Inteligência:** {intelligence_level} IQ\n\n" \
                                     f"| Data | Missão | Tokens | Custo Est. | Status |\n" \
                                     f"| :--- | :--- | :--- | :--- | :--- |\n{new_entry}"
                updated_content = content + dashboard_template
                
            readme_path.write_text(updated_content, encoding='utf-8')
        except Exception as e:
            logger.warning(f"⚠️ Erro ao atualizar dashboard: {e}")

    def _reactive_mutation(self, mission_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica a mutação de código real nos arquivos alvo"""
        logger.info("⚡ Executando Mutação Autônoma...")
        files_changed = []
        api_key = os.getenv('GROQ_API_KEY')

        for file_path_str in mission_analysis.get('target_files', []):
            file_path = self.repo_path / file_path_str
            if not file_path.exists(): continue
            
            current_code = file_path.read_text(encoding='utf-8')
            prompt = f"""
            Como Programador Sênior, implemente as seguintes ações no código abaixo:
            AÇÕES: {mission_analysis.get('required_actions')}
            
            REGRAS:
            - Retorne APENAS o código completo atualizado.
            - Não use blocos de Markdown (```).
            - Mantenha a compatibilidade com os testes existentes.

            CÓDIGO ATUAL:
            {current_code}
            """

            
            try:
                import requests
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "llama3-70b-8192",
                        "messages": [
                            {"role": "system", "content": "Você é um programador sênior. Responda APENAS com o código puro, sem markdown."},
                            {"role": "user", "content": prompt}
                        ]
                    }
                )
                new_code = resp.json()['choices'][0]['message']['content']
                new_code = re.sub(r'```python\n|```', '', new_code)
                
                file_path.write_text(new_code.strip(), encoding='utf-8')
                files_changed.append(file_path_str)
            except Exception as e:
                logger.error(f"❌ Erro ao mutar {file_path_str}: {e}")

        return {
            'success': len(files_changed) > 0,
            'mutation_applied': len(files_changed) > 0,
            'files_changed': files_changed
        }

    def apply_mutation(self, strategy: str, intent: str, impact: str, roadmap_context: str = None) -> Dict[str, Any]:
        """Coordena o ciclo de mutação"""
        issue_body = os.getenv('ISSUE_BODY', 'Evolução Contínua')
        
        # 1. Brainstorm
        analysis = self._engineering_brainstorm(issue_body, roadmap_context or "")
        
        # 2. Executa
        if analysis.get('can_auto_implement'):
            result = self._reactive_mutation(analysis)
        else:
            result = self._create_manual_marker(intent, impact, issue_body)

        # 3. Telemetria e Dashboard
        if result.get('success'):
            usage = analysis.get('usage', {})
            self._update_evolution_dashboard(
                mission_name=analysis.get('mission_type', intent),
                tokens=usage.get('total_tokens', 0),
                cost=usage.get('cost', 0.0)
            )
        
        self._save_mutation_log(strategy, intent, impact, result)
        self._export_to_github_actions(result)
        return result

    def _create_manual_marker(self, intent: str, impact: str, issue_body: str) -> Dict[str, Any]:
        """Cria marcador se a automação falhar"""
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

# --- MAIN ---
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
