
from dataclasses import dataclass
from typing import Dict

@dataclass
class SystemState:
    '''Classe para representar o estado do sistema'''
    components: Dict[str, str]
    services: Dict[str, str]
    resources: Dict[str, str]

    def update_component(self, component_name: str, component_status: str):
        '''Atualiza o status de um componente'''
        self.components[component_name] = component_status

    def update_service(self, service_name: str, service_status: str):
        '''Atualiza o status de um serviço'''
        self.services[service_name] = service_status

    def update_resource(self, resource_name: str, resource_status: str):
        '''Atualiza o status de um recurso'''
        self.resources[resource_name] = resource_status

    def get_component_status(self, component_name: str) -> str:
        '''Retorna o status de um componente'''
        return self.components.get(component_name)

    def get_service_status(self, service_name: str) -> str:
        '''Retorna o status de um serviço'''
        return self.services.get(service_name)

    def get_resource_status(self, resource_name: str) -> str:
        '''Retorna o status de um recurso'''
        return self.resources.get(resource_name)
