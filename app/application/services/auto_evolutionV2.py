from app.core.nexus import nexus, NexusComponent
from app.utils.document_store import document_store
from pathlib import Path
from typing import List, Dict, Optional
import logging
logger = logging.getLogger(__name__)

class AutoEvolutionServiceV2(NexusComponent):
    """
    Versão Evoluída: Migração de Roadmap Markdown para Inventário de Capacidades .JRVS.
    Localização: data/capabilities.jrvs
    """

    def __init__(self, capabilities_path: str = "data/capabilities.jrvs") -> None:
        super().__init__()
        # Define o caminho relativo ao root do projeto
        self.capabilities_path = Path(capabilities_path)

    def execute(self, context: Optional[Dict] = None) -> Dict:
        """
        Despacha ações baseadas em context["action"]:
          "status"      → get_success_metrics()
          "find_next"   → find_next_mission()
          "evolve_next" | "evolve_cap" → evolve uma cap pelo evolution_orchestrator
        """
        if not context:
            context = {}

        action = context.get("action", "status")

        try:
            if action == "status":
                metrics = self.get_success_metrics()
                return {"success": True, "action": action, "metrics": metrics}

            if action == "find_next":
                mission = self.find_next_mission()
                return {"success": True, "action": action, "mission": mission}

            if action in ("evolve_next", "evolve_cap"):
                cap_id = context.get("cap_id")
                if not cap_id:
                    mission = self.find_next_mission()
                    if not mission:
                        return {"success": False, "error": "Nenhuma cap pendente encontrada."}
                    cap_id = mission["id"]
                else:
                    mission = next(
                        (
                            c
                            for c in self._load_data().get("capabilities", [])
                            if c.get("id") == cap_id
                        ),
                        None,
                    )
                    if mission is None:
                        return {
                            "success": False,
                            "error": f"Capability {cap_id} não encontrada no inventário.",
                            "cap_id": cap_id,
                        }

                roadmap_context = context.get("roadmap_context") or self.get_roadmap_context(mission)
                max_attempts = context.get("max_attempts", 3)
                return self._evolve_capability(cap_id, mission, roadmap_context, max_attempts)

            return {"success": False, "error": f"Ação desconhecida: {action!r}"}

        except Exception as exc:
            logger.error("[AutoEvolutionV2] execute() falhou: %s", exc)
            return {"success": False, "error": str(exc)}

    def _evolve_capability(
        self, cap_id: str, mission: Optional[Dict], roadmap_context: str, max_attempts: int = 3
    ) -> Dict:
        """Evolui uma capability através do EvolutionOrchestrator (via Nexus).

        O antigo motor ``scripts/evolution_mutator.py`` foi removido do projeto;
        o caminho vivo de mutação é o ``EvolutionOrchestrator``, que gera o patch
        via MetabolismCore, valida a sintaxe, salva a proposta em
        ``data/evolution_proposals/`` e abre o PR pelo GitHubWorker.

        Args:
            cap_id: identificador da capability-alvo (ex.: ``CAP-042``).
            mission: metadados da capability (título/notas) ou ``None``.
            roadmap_context: contexto textual já montado para o LLM.
            max_attempts: número máximo de ciclos de evolução tentados.
        """
        try:
            orchestrator = nexus.resolve("evolution_orchestrator")
        except Exception as exc:
            logger.error("[AutoEvolutionV2] evolution_orchestrator indisponível: %s", exc)
            return {"success": False, "error": str(exc), "cap_id": cap_id}

        if orchestrator is None or not hasattr(orchestrator, "execute"):
            return {
                "success": False,
                "error": "evolution_orchestrator indisponível no Nexus.",
                "cap_id": cap_id,
            }

        attempts = max(1, int(max_attempts or 1))
        last_result: Dict = {}
        for attempt in range(1, attempts + 1):
            last_result = orchestrator.execute(
                {
                    "cap_id": cap_id,
                    "cap_title": (mission or {}).get("title", ""),
                    "mission_id": cap_id,
                    "roadmap_context": roadmap_context,
                }
            ) or {}
            if last_result.get("success"):
                return {
                    "success": True,
                    "evolved": cap_id,
                    "attempts": attempt,
                    "result": last_result,
                }
            logger.warning(
                "[AutoEvolutionV2] Tentativa %d/%d de evoluir %s falhou: %s",
                attempt,
                attempts,
                cap_id,
                last_result.get("reason") or last_result.get("error"),
            )

        return {
            "success": False,
            "error": f"Evolução de {cap_id} falhou após {attempts} tentativas.",
            "cap_id": cap_id,
            "last_result": last_result,
        }

    def _resolved_path(self) -> Path:
        """Caminho efetivo do inventário de capacidades.

        Prefere o caminho configurado (``.jrvs``) quando ele existe no disco e,
        caso contrário, cai para o irmão ``.json``/``.jrvs`` equivalente. Sem esse
        fallback o serviço respondeia "empty_inventory" (nenhuma missão pendente)
        mesmo com o inventário completo disponível em ``capabilities.json``.
        """
        path = self.capabilities_path
        if path.exists():
            return path
        for alt_suffix in (".json", ".jrvs"):
            alt = path.with_suffix(alt_suffix)
            if alt != path and alt.exists():
                logger.warning(
                    "[AutoEvolutionV2] %s não encontrado — usando %s", path, alt
                )
                return alt
        return path

    def _load_data(self) -> Dict:
        """Carrega o inventário de capacidades."""
        path = self._resolved_path()
        if not path.exists():
            return {"capabilities": []}
        try:
            return document_store.read(path)
        except Exception:
            return {"capabilities": []}

    def _save_data(self, data: Dict):
        """Persiste as atualizações no inventário (mesmo formato lido)."""
        document_store.write(self._resolved_path(), data)

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
