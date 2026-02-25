from app.core.nexuscomponent import NexusComponent

import json
from typing import List, Dict

class Capability(NexusComponent):
    def execute(self, context: dict):
        raise NotImplementedError("Implementação automática via Cristalizador")

    def __init__(self, id: str, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description

class CAP020:
    def __init__(self):
        self.capabilities = []

    def add_capability(self, capability: Capability):
        self.capabilities.append(capability)

    def identify_redundant_capabilities(self) -> List[Dict]:
        redundant_capabilities = []
        unique_capabilities = {}

        for capability in self.capabilities:
            if capability.name in unique_capabilities:
                redundant_capabilities.append({
                    'id': capability.id,
                    'name': capability.name,
                    'description': capability.description
                })
            else:
                unique_capabilities[capability.name] = capability

        return redundant_capabilities

# Exemplo de uso
cap020 = CAP020()

capability1 = Capability('1', 'Capabilidade 1', 'Descrição da capabilidade 1')
capability2 = Capability('2', 'Capabilidade 2', 'Descrição da capabilidade 2')
capability3 = Capability('3', 'Capabilidade 1', 'Descrição da capabilidade 1')

cap020.add_capability(capability1)
cap020.add_capability(capability2)
cap020.add_capability(capability3)

redundant_capabilities = cap020.identify_redundant_capabilities()

print(json.dumps(redundant_capabilities, indent=4))

# Nexus Compatibility
Cap020IdentifyRedundantCapabilities = Capability
