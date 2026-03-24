# -*- coding: utf-8 -*-
"""MacroDroid Adapter — Comunicação Bidirecional JARVIS ↔ Android.
ARQUITETURA: Edge Soldier do JARVIS (telemetry + comando).
"""
import logging
import requests
from typing import Dict, Any, Optional
from app.core.nexus import NexusComponent
from app.domain.ports.device_control_port import DeviceControlPort, DeviceIntent

logger = logging.getLogger(__name__)


class MacroDroidAdapter(NexusComponent, DeviceControlPort):
    """
    Adapter bidirecional para MacroDroid.
    
    Funcionalidades:
    - Envia comandos para o dispositivo
    - Recebe telemetry (battery, location, network, etc.)
    - Cache de status do dispositivo
    """
    
    def __init__(self, device_id: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__()
        self.device_id = device_id or ""
        self.api_key = api_key or ""
        self.base_url = "https://trigger.macrodroid.com"
        self._device_cache: Dict[str, Any] = {}
        self._cache_ttl = 300  # 5 minutos
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return bool(self.device_id and self.api_key)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point via Nexus DI."""
        ctx = context or {}
        action = ctx.get("action")
        
        if action == "get_telemetry":
            return self.get_device_telemetry()
        elif action == "execute_command":
            intent = DeviceIntent(
                action=ctx.get("command_action"),
                device_id=ctx.get("device_id", self.device_id),
                 ctx.get("command_data"),
                timeout=ctx.get("timeout", 5)
            )
            return self.execute_intent(intent)
        else:            # Default: execute command
            intent = DeviceIntent(
                action=action,
                device_id=self.device_id,
                 ctx.get("params", {}).get("data")
            )
            return self.execute_intent(intent)
    
    def execute_intent(self, intent: DeviceIntent) -> Dict[str, Any]:
        """
        Envia comando E recebe telemetry de volta.
        """
        if not intent.device_id:
            return {"success": False, "error": "device_id obrigatório"}
        
        # URL do webhook universal
        webhook_url = f"{self.base_url}/{intent.device_id}/jarvis-exec"
        
        # Payload com ação + solicitação de telemetry
        payload = {
            "action": intent.action,
            "request_telemetry": "true",  # ← Solicita dados de volta
            "callback_id": f"jarvis_{intent.action}_{id(intent)}"
        }
        
        if intent.
            payload.update(intent.data)
        
        try:
            response = requests.get(
                webhook_url,
                params=payload,
                timeout=intent.timeout,
                headers={"User-Agent": "JARVIS-Xerife/2.0"}
            )
            
            if response.status_code == 200:
                # MacroDroid pode retornar JSON com telemetry
                try:
                    result_data = response.json()
                    telemetry = result_data.get("telemetry", {})
                    
                    # Atualiza cache do dispositivo
                    self._update_device_cache(telemetry)
                    
                    return {
                        "success": True,
                        "message": result_data.get("message", "Ação executada"),
                        "action": intent.action,
                        "device_id": intent.device_id,                        "telemetry": telemetry  # ← Dados do dispositivo
                    }
                except:
                    # Resposta simples (sem JSON)
                    return {
                        "success": True,
                        "message": "Ação executada",
                        "action": intent.action,
                        "device_id": intent.device_id
                    }
            else:
                return {
                    "success": False,
                    "message": f"MacroDroid retornou status {response.status_code}",
                    "action": intent.action
                }
                
        except requests.Timeout:
            return {"success": False, "error": "Timeout - dispositivo offline?"}
        except requests.ConnectionError:
            return {"success": False, "error": "Erro de conexão - celular offline?"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_device_telemetry(self) -> Dict[str, Any]:
        """
        Coleta telemetry completa do dispositivo.
        """
        if not self.device_id:
            return {"success": False, "error": "device_id não configurado"}
        
        # Webhook específico para telemetry
        telemetry_url = f"{self.base_url}/{self.device_id}/jarvis-telemetry"
        
        try:
            response = requests.get(telemetry_url, timeout=10)
            
            if response.status_code == 200:
                telemetry = response.json() if response.text else {}
                self._update_device_cache(telemetry)
                
                return {
                    "success": True,
                    "telemetry": telemetry,
                    "device_id": self.device_id,
                    "cached_at": telemetry.get("timestamp")
                }
            else:
                return {"success": False, "error": f"Status {response.status_code}"}
                        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _update_device_cache(self, telemetry: Dict[str, Any]) -> None:
        """Atualiza cache local com dados do dispositivo."""
        import time
        self._device_cache = {
            **telemetry,
            "_last_update": time.time(),
            "_ttl": self._cache_ttl
        }
    
    def get_cached_telemetry(self) -> Optional[Dict[str, Any]]:
        """Retorna telemetry em cache (se não expirou)."""
        import time
        if not self._device_cache:
            return None
        
        last_update = self._device_cache.get("_last_update", 0)
        if time.time() - last_update > self._cache_ttl:
            return None
        
        return {k: v for k, v in self._device_cache.items() if not k.startswith("_")}
    
    def is_available(self, device_id: str) -> bool:
        """Verifica disponibilidade via ping."""
        ping_url = f"{self.base_url}/{device_id}/jarvis-ping"
        try:
            response = requests.get(ping_url, timeout=3)
            return response.status_code == 200
        except:
            return False


# Compatibilidade
MacroDroid = MacroDroidAdapter