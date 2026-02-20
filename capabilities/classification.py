
import enum

from dataclasses import dataclass

from typing import List



class CapabilityStatus(enum.Enum):
    NONEXISTENT = 1
    PARTIAL = 2
    COMPLETE = 3


@dataclass
class Capability:
    name: str
    status: CapabilityStatus


class CapabilityClassifier:
    def __init__(self):
        self.capabilities = {}

    def add_capability(self, capability: Capability):
        self.capabilities[capability.name] = capability

    def classify_capabilities(self) -> dict:
        classified_capabilities = {status: [] for status in CapabilityStatus}
        for capability in self.capabilities.values():
            classified_capabilities[capability.status].append(capability.name)
        return classified_capabilities


# Exemplo de uso:

classifier = CapabilityClassifier()

classifier.add_capability(Capability("JARVIS", CapabilityStatus.COMPLETE))

classifier.add_capability(Capability("SARA", CapabilityStatus.PARTIAL))

classifier.add_capability(Capability("ALEXA", CapabilityStatus.NONEXISTENT))

print(classifier.classify_capabilities())