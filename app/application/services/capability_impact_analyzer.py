
import networkx as nx
from typing import Dict, List

class CapabilityImpactAnalyzer:
    def __init__(self, capabilities: Dict[str, List[str]]):
        self.capabilities = capabilities
        self.graph = nx.DiGraph()

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

# Exemplo de uso:
capabilities = {
    'capability1': ['capability2', 'capability3'],
    'capability2': ['capability4'],
    'capability3': ['capability5']
}

analyzer = CapabilityImpactAnalyzer(capabilities)
summary = analyzer.get_impact_summary('capability1')
print(summary)
   