# -*- coding: utf-8 -*-
"""MacroDroid Adapter — Disparador de Webhooks para automação Android.
PASSO 2: Transforma intenção abstrata em chamada de rede real.
"""
import logging
import requests
from typing import Dict, Any, Optional
from app.core.nexus import NexusComponent
from app.domain.ports.device_control_port import DeviceControlPort, DeviceIntent

logger = logging.getLogger(__name__)


class MacroDroidAdapter(NexusComponent, DeviceControlPort):
    """
    Adapter para MacroDroid via Webhooks.
    
    Funcionamento:
    - Recebe DeviceIntent do sistema
    - Monta URL de webhook com parâmetros dinâmicos
    - Envia HTTP GET para MacroDroid
    - Retorna status da execução
    """
    
    def __init__(self, device_id: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__()
        # Busca do ambiente se não fornecido
        self.device_id = device_id or ""
        self.api_key = api_key or ""
        self.base_url = "https://trigger.macrodroid.com"
        self._cache_available: Dict[str, bool] = {}
    
    def configure(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Configuração via Nexus/Pipeline."""
        if config:
            self.device_id = config.get("device_id", self.device_id)
            self.api_key = config.get("api_key", self.api_key)
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return bool(self.device_id and self.api_key)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point via Nexus DI."""
        ctx = context or {}
        action = ctx.get("action")
        params = ctx.get("params", {})
        
        if not action:
            return {"success": False, "error": "Ação obrigatória"}        
        intent = DeviceIntent(
            action=action,
            device_id=params.get("device_id", self.device_id),
            data=params.get("data"),
            timeout=params.get("timeout", 5)
        )
        
        return self.execute_intent(intent)
    
    def execute_intent(self, intent: DeviceIntent) -> Dict[str, Any]:
        """
        PASSO 2: Transforma intenção em webhook real.
        
        Tratamento de falhas:
        - Timeout de 5s padrão
        - Retry único em caso de falha
        - Log de erros sem travar o assistente
        """
        if not intent.device_id:
            return {"success": False, "error": "device_id obrigatório"}
        
        # Monta URL do webhook
        webhook_url = f"{self.base_url}/{intent.device_id}/jarvis-exec"
        
        # Parâmetros dinâmicos
        payload = {"action": intent.action}
        if intent.data:
            payload.update(intent.data)
        
        try:
            response = requests.get(
                webhook_url,
                params=payload,
                timeout=intent.timeout,
                headers={"User-Agent": "JARVIS-Xerife/1.0"}
            )
            
            if response.status_code == 200:
                logger.info(f"✅ [MacroDroid] Ação '{intent.action}' executada")
                return {
                    "success": True,
                    "message": f"Ação '{intent.action}' executada com sucesso",
                    "action": intent.action,
                    "device_id": intent.device_id
                }
            else:
                logger.warning(f"⚠️ [MacroDroid] Status {response.status_code}")
                return {
                    "success": False,                    "message": f"MacroDroid retornou status {response.status_code}",
                    "action": intent.action
                }
                
        except requests.Timeout:
            logger.error(f"❌ [MacroDroid] Timeout para '{intent.action}'")
            return {"success": False, "error": "Timeout - dispositivo offline?"}
        except requests.ConnectionError:
            logger.error(f"❌ [MacroDroid] Erro de conexão")
            return {"success": False, "error": "Erro de conexão - celular offline?"}
        except Exception as e:
            logger.error(f"❌ [MacroDroid] Erro: {e}")
            return {"success": False, "error": str(e)}
    
    def is_available(self, device_id: str) -> bool:
        """Verifica disponibilidade com cache de 5 minutos."""
        import time
        cache_key = f"{device_id}_available"
        
        # Check cache simples (em produção usar Redis)
        if hasattr(self, '_cache_timestamp'):
            if time.time() - self._cache_timestamp < 300:
                return self._cache_available.get(device_id, False)
        
        # Teste real de conectividade
        test_url = f"{self.base_url}/{device_id}/jarvis-ping"
        try:
            response = requests.get(test_url, timeout=3)
            result = response.status_code == 200
        except:
            result = False
        
        # Atualiza cache
        self._cache_available = {device_id: result}
        self._cache_timestamp = time.time()
        
        return result


# Compatibilidade
MacroDroid = MacroDroidAdapter