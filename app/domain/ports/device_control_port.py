# -*- coding: utf-8 -*-
"""Device Control Port — Contrato abstrato para controle de dispositivo.
PASSO 1: Interface que abstrai o controle do dispositivo Android.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class DeviceIntent:
    """Intenção de controle de dispositivo.
    
    Attributes:
        action: Ação principal (ex: 'flashlight', 'open_app', 'silent_mode')
        data: Dado extra opcional (ex: nome do pacote, valor de configuração)
        device_id: Identificador único do dispositivo MacroDroid
    """
    action: str
    device_id: str
    data: Optional[Dict[str, Any]] = None
    timeout: int = 5


class DeviceControlPort(ABC):
    """Contrato abstrato para controle de dispositivo Android.
    
    Esta interface permite que o núcleo da aplicação não dependa
    de nenhuma ferramenta específica de automação (MacroDroid, Tasker, etc.)
    """
    
    @abstractmethod
    def execute_intent(self, intent: DeviceIntent) -> Dict[str, Any]:
        """
        Executa uma intenção de controle no dispositivo.
        
        Args:
            intent: Intenção com ação, dados e device_id
            
        Returns:
            Dict com status da execução:
            - success: bool
            - message: str
            - action: str
            - device_id: str
        """
        pass
    
    @abstractmethod
    def is_available(self, device_id: str) -> bool:
        """Verifica se dispositivo está disponível/online."""
        pass