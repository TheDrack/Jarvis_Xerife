from app.core.nexus import NexusComponent

import networkx as nx
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class CapabilityImpactAnalyzer(NexusComponent):
    def __init__(self, capabilities: Optional[Dict[str, List[str]]] = None):
        self.capabilities: Dict[str, List[str]] = capabilities or {}
        self.graph = nx.DiGraph()

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ponto de entrada Nexus para análise de impacto de capabilities.

        Ações suportadas via ``context["action"]``:
            ``"build_graph"`` — reconstrói o grafo de dependências.
            ``"analyze"``     — retorna o resumo de impacto de ``context["capability"]``.
        """
        ctx = context or {}
        action = ctx.get("action")

        if action == "build_graph":
            self.build_graph()
            return {"success": True, "action": "build_graph", "nodes": list(self.graph.nodes)}

        if action == "analyze":
            capability = ctx.get("capability")
            if not capability:
                return {"success": False, "error": "Campo 'capability' obrigatório para action='analyze'"}
            summary = self.get_impact_summary(capability)
            return {"success": True, **summary}

        return {"success": False, "error": "action inválida — use 'build_graph' ou 'analyze'"}

    def build_graph(self):
        for capability, impacted_capabilities in self.capabilities.items():
            for impacted_capability in impacted_capabilities:
                self.graph.add_edge(capability, impacted_capability)

    def analyze_impact(self, capability: str):
        self.build_graph()
        impacted_capabilities = list(self.graph.successors(capability))
        return impacted_capabilities

    def get_impact_summary(self, capability: str):
        impacted_capabilities = self.analyze_impact(capability)
        summary = {
            'capability': capability,
            'impacted_capabilities': impacted_capabilities
        }
        return summary


if __name__ == "__main__":
    # Exemplo de uso:
    capabilities = {
        'capability1': ['capability2', 'capability3'],
        'capability2': ['capability4'],
        'capability3': ['capability5']
    }

    analyzer = CapabilityImpactAnalyzer(capabilities)
    summary = analyzer.get_impact_summary('capability1')
    print(summary)
   