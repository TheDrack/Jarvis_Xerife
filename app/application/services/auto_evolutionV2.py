import json
import os
from pathlib import Path
from typing import List, Dict, Optional

class AutoEvolutionService:
    def __init__(self, capabilities_path="data/capabilities.json"):
        self.capabilities_path = Path(capabilities_path)
        # Fallback para garantir que o diretório exista
        self.capabilities_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_data(self) -> Dict:
        """Carrega o JSON de capacidades de forma segura."""
        if not self.capabilities_path.exists():
            return {"capabilities": []}
        try:
            return json.loads(self.capabilities_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, Exception):
            return {"capabilities": []}

    def _save_data(self, data: Dict):
        """Persiste as alterações no JSON."""
        self.capabilities_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), 
            encoding='utf-8'
        )

    def is_auto_evolution_pr(self, title: str, body: str = "") -> bool:
        content = f"{title} {body if body else ''}".lower()
        targets = ["auto evolution", "auto-evolution", "jarvis", "self-evolution", "capability-update"]
        return any(t in content for t in targets)

    def get_success_metrics(self):
        data = self._load_data()
        caps = data.get("capabilities", [])
        total = len(caps)
        completed = len([c for c in caps if c.get("status") == "complete"])
        
        return {
            "missions_completed": completed,
            "total_missions": total,
            "evolution_rate": round(completed / total, 4) if total > 0 else 1.0,
            "error": None if total > 0 else "Capabilities file empty or not found"
        }

    def find_next_mission(self) -> Optional[Dict]:
        """
        Identifica a próxima missão lógica baseada em:
        1. Status (não completo)
        2. Prioridade (menor valor numérico = maior urgência)
        3. Dependências (só libera se as dependências estiverem 'complete')
        """
        data = self._load_data()
        caps = data.get("capabilities", [])
        
        # Filtrar apenas o que não está pronto
        pending = [c for c in caps if c.get("status") != "complete"]
        
        # Ordenar por prioridade
        pending.sort(key=lambda x: x.get("priority", 99))

        for cap in pending:
            deps = cap.get("depends_on", [])
            # Checar se todas as dependências estão completas
            if self._are_dependencies_met(caps, deps):
                return {
                    "mission": cap,
                    "id": cap.get("id"),
                    "description": cap.get("title"),
                    "section": cap.get("notes", "General"),
                    "priority": cap.get("priority")
                }
        return None

    def _are_dependencies_met(self, all_caps: List[Dict], dependencies: List[str]) -> bool:
        if not dependencies:
            return True
        completed_ids = {c["id"] for c in all_caps if c.get("status") == "complete"}
        return all(dep_id in completed_ids for dep_id in dependencies)

    def mark_mission_as_completed(self, capability_id: str) -> bool:
        """Atualiza o status de uma capacidade específica para 'complete'."""
        data = self._load_data()
        updated = False
        
        for cap in data.get("capabilities", []):
            if cap.get("id") == capability_id or cap.get("title") == capability_id:
                cap["status"] = "complete"
                updated = True
                break
        
        if updated:
            self._save_data(data)
        return updated

    def get_roadmap_context(self, mission_data: Dict) -> str:
        if not mission_data: return "No mission context available"
        cap = mission_data.get('mission', mission_data)
        return (
            f"IDENTIFICADOR: {cap.get('id')}\n"
            f"CAPACIDADE: {cap.get('title')}\n"
            f"DESCRIÇÃO: {cap.get('description')}\n"
            f"DEPENDÊNCIAS: {', '.join(cap.get('depends_on', []))}\n"
            f"STATUS ATUAL: {cap.get('status')}"
        )
