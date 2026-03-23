from abc import ABC, abstractmethod
from typing import Optional

class DeviceControlPort(ABC):
    """
    Contrato para envio de comandos físicos ou lógicos para o dispositivo do usuário.
    """
    
    @abstractmethod
    async def execute_intent(self, action: str, data: Optional[str] = None) -> bool:
        """
        Envia uma intenção (Intent) para o dispositivo.
        
        :param action: Ação a ser executada (ex: 'torch_toggle', 'launch_app').
        :param data: Dados adicionais, como nome do pacote (ex: 'com.whatsapp').
        :return: True se a requisição foi enviada com sucesso.
        """
        pass
