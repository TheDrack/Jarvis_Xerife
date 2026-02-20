
import json

from enum import Enum



class CapabilityStatus(Enum):

    NONEXISTENT = 1

    PARTIAL = 2

    COMPLETE = 3



class Capability:

    def __init__(self, name, status):

        self.name = name

        self.status = status



class CapabilitiesClassifier:

    def __init__(self):

        self.capabilities = {}



    def add_capability(self, capability):

        self.capabilities[capability.name] = capability



    def classify_capabilities(self):

        classified_capabilities = {

            'nonexistent': [],

            'partial': [],

            'complete': []

        }



        for capability in self.capabilities.values():

            if capability.status == CapabilityStatus.NONEXISTENT:

                classified_capabilities['nonexistent'].append(capability.name)

            elif capability.status == CapabilityStatus.PARTIAL:

                classified_capabilities['partial'].append(capability.name)

            elif capability.status == CapabilityStatus.COMPLETE:

                classified_capabilities['complete'].append(capability.name)



        return classified_capabilities



# Exemplo de uso:

classifier = CapabilitiesClassifier()

classifier.add_capability(Capability('capability1', CapabilityStatus.COMPLETE))

classifier.add_capability(Capability('capability2', CapabilityStatus.PARTIAL))

classifier.add_capability(Capability('capability3', CapabilityStatus.NONEXISTENT))



classified_capabilities = classifier.classify_capabilities()

print(json.dumps(classified_capabilities, indent=4))

