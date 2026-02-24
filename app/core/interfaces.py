# app/core/interfaces.py
from abc import ABC, abstractmethod

class NexusComponent(ABC):
    """Interface obrigatória para descoberta via JarvisNexus"""
    @abstractmethod
    def execute(self, *args, **kwargs):
        pass

# Nexus Compatibility
Interfaces = NexusComponent
