from app.core.nexuscomponent import NexusComponent
import json
from pathlib import Path
from typing import List, Dict, Optional

class AutoEvolutionServiceV2(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    """
    Versão Evoluída: Migração de Roadmap Markdown para Inventário de Capacidades JSON.
    Localização: data/capabilities.json
    """
    def __init__(self, capabilities_path="data/capabilities.json"):
        # Define o caminho relativo ao root do projeto
        self.capabilities_path = Path(capabilities_path)

    def _load_data(self) -> Dict:
        """Carrega o inventário de capacidades."""
        if not self.capabilities_path.exists():
            return {"capabilities": []}
        try:
            return json.loads(self.capabilities_path.read_text(encoding='utf-8'))
        except Exception:
            return {"capabilities": []}

    def _save_data(self, data: Dict):
        """Persiste as atualizações no JSON."""
        self.capabilities_path.parent.mkdir(parents=True, exist_ok=True)
        self.capabilities_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), 
            encoding='utf-8'
        )

    def get_success_metrics(self) -> Dict:
        """Calcula métricas reais baseadas nos itens de capacidade."""
        data = self._load_data()
        caps = data.get("capabilities", [])
        total = len(caps)
        completed = len([c for c in caps if c.get("status") == "complete"])

        return {
            "missions_completed": completed,
            "total_missions": total,
            "evolution_rate": round(completed / total, 4) if total > 0 else 0.0,
            "status": "operational" if total > 0 else "empty_inventory"
        }

    def find_next_mission(self) -> Optional[Dict]:
        """
        Algoritmo de seleção baseado em Dependências e Prioridade.
        """
        data = self._load_data()
        caps = data.get("capabilities", [])
        completed_ids = {c["id"] for c in caps if c.get("status") == "complete"}

        pending = [c for c in caps if c.get("status") != "complete"]
        # Prioridade 1 vem antes de 2
        pending.sort(key=lambda x: x.get("priority", 99))

        for cap in pending:
            deps = cap.get("depends_on", [])
            if not deps or all(d in completed_ids for d in deps):
                # Retornamos o objeto completo para o contexto
                return {
                    "mission": cap,
                    "id": cap.get("id"),
                    "title": cap.get("title"),
                    "description": cap.get("description", ""),
                    "notes": cap.get("notes", "N/A"),
                    "priority": cap.get("priority", 3)
                }
        return None

    def get_roadmap_context(self, mission_data: Dict) -> str:
        """
        Transforma os dados da missão em texto para a IA.
        Soluciona o erro: 'AutoEvolutionServiceV2' object has no attribute 'get_roadmap_context'
        """
        if not mission_data:
            return "No mission context available"
        
        # Extrai a missão do dicionário retornado pelo find_next_mission
        cap = mission_data.get('mission', mission_data)
        
        return (
            f"IDENTIFICADOR: {cap.get('id')}\n"
            f"CAPACIDADE: {cap.get('title')}\n"
            f"DESCRIÇÃO: {cap.get('description')}\n"
            f"DEPENDÊNCIAS: {', '.join(cap.get('depends_on', []))}\n"
            f"NOTAS/CAPÍTULO: {cap.get('notes', 'N/A')}\n"
            f"STATUS: {cap.get('status', 'pending')}"
        )

    def mark_mission_as_completed(self, cap_id: str) -> bool:
        """Atualiza o status no JSON usando o ID único."""
        data = self._load_data()
        found = False
        for cap in data.get("capabilities", []):
            if cap.get("id") == cap_id:
                cap["status"] = "complete"
                found = True
                break

        if found:
            self._save_data(data)
        return found

    def is_auto_evolution_pr(self, title: str) -> bool:
        """Detecta se um PR/Commit é parte do nosso ciclo de evolução."""
        return any(term in title.lower() for term in ["auto-evolution", "jarvis", "capability"])

# Nexus Compatibility
AutoEvolutionv2 = AutoEvolutionServiceV2
