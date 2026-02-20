import os, re
from pathlib import Path

class AutoEvolutionService:
    def __init__(self, roadmap_path="docs/ROADMAP.md"):
        self.roadmap_path = Path(roadmap_path)

    def parse_roadmap_missions(self):
        """Varre o ROADMAP e extrai missões pendentes (🔄 ou 📋)."""
        if not self.roadmap_path.exists():
            return []
        
        content = self.roadmap_path.read_text(encoding='utf-8')
        missions = []
        # Regex para capturar linhas que começam com 🔄 ou 📋
        pattern = re.compile(r"[-*+]\s*([🔄📋])\s*(.*)")
        
        current_section = "Geral"
        for line in content.split('\n'):
            if line.startswith('## '):
                current_section = line.replace('## ', '').strip()
            
            match = pattern.search(line)
            if match:
                status_icon = match.group(1)
                desc = match.group(2).strip()
                missions.append({
                    "description": desc,
                    "status": "in_progress" if status_icon == "🔄" else "planned",
                    "section": current_section
                })
        return missions

    def find_next_mission(self):
        """Busca a primeira missão pendente no Roadmap."""
        missions = self.parse_roadmap_missions()
        # Prioriza as missões 'in_progress' (🔄), depois 'planned' (📋)
        pending = [m for m in missions if m['status'] == 'in_progress']
        if not pending:
            pending = [m for m in missions if m['status'] == 'planned']
            
        if not pending:
            return None

        target = pending[0]
        return {
            "mission": target,
            "description": target['description'],
            "section": target['section'],
            "priority": "high" if target['status'] == 'in_progress' else "medium"
        }

    def find_next_mission_with_auto_complete(self):
        # Alias para compatibilidade com seu workflow
        return self.find_next_mission()

    def mark_mission_as_completed(self, mission_description: str) -> bool:
        """Troca o ícone da missão para ✅ no ROADMAP."""
        if not self.roadmap_path.exists(): return False
        content = self.roadmap_path.read_text(encoding='utf-8')
        
        # Escapa caracteres especiais da descrição para o Regex
        safe_desc = re.escape(mission_description)
        # Procura por 🔄 ou 📋 seguido da descrição
        pattern = rf"([🔄📋])\s*{safe_desc}"
        
        if re.search(pattern, content):
            # Substitui qualquer um dos ícones por ✅
            new_content = re.sub(pattern, f"✅ {mission_description}", content)
            self.roadmap_path.write_text(new_content, encoding='utf-8')
            print(f"✅ Roadmap atualizado: {mission_description}")
            return True
        return False

    def get_roadmap_context(self, mission_data):
        if not mission_data: return "No mission context available"
        mission = mission_data.get('mission', mission_data)
        return (f"MISSÃO ATUAL: {mission.get('description')}\n"
                f"SEÇÃO: {mission.get('section')}\n"
                f"STATUS: {mission.get('status')}")
