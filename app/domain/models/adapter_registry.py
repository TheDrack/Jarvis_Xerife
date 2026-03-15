# -*- coding: utf-8 -*-
"""AdapterRegistry — Registro simplificado do que o Jarvis PODE fazer.

Diferença do consolidated context:
- Consolidated: CÓDIGO COMPLETO (500KB+)
- AdapterRegistry: LISTA DE HABILIDADES (5KB)
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)


@dataclass
class AdapterInfo:
    """Informação simplificada de um adapter."""
    adapter_id: str
    name: str
    description: str
    capabilities: List[str]
    config_keys: List[str]
    example_yaml: str
    exists: bool = True
    
    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "config_keys": self.config_keys,
            "example_yaml": self.example_yaml,
            "exists": self.exists,
        }


class AdapterRegistry(NexusComponent):
    """Registro de adapters disponíveis no Jarvis."""
    
    def __init__(self):
        super().__init__()
        self._cache: Optional[Dict[str, AdapterInfo]] = None
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = context or {}
        action = ctx.get("action", "list")
                if action == "list":
            return {"success": True, "adapters": self.list_adapters()}
        elif action == "get":
            adapter_id = ctx.get("adapter_id")
            return {"success": True, "adapter": self.get_adapter(adapter_id)}
        elif action == "find_gap":
            capability = ctx.get("capability")
            return {"success": True, "gap": self.find_gap(capability)}
        elif action == "refresh":
            self._cache = None
            return {"success": True, "adapters": self.list_adapters()}
        
        return {"success": False, "error": "Ação não reconhecida"}
    
    def list_adapters(self) -> List[Dict[str, Any]]:
        """Lista todos os adapters disponíveis."""
        if self._cache:
            return [v.to_dict() for v in self._cache.values()]
        
        adapters = self._get_known_adapters()
        discovered = self._discover_adapters()
        
        for disc in discovered:
            if not any(a["adapter_id"] == disc["adapter_id"] for a in adapters):
                adapters.append(disc)
        
        self._cache = {a["adapter_id"]: AdapterInfo(**a) for a in adapters}
        return [a.to_dict() for a in self._cache.values()]
    
    def get_adapter(self, adapter_id: str) -> Optional[Dict[str, Any]]:
        """Obtém informação de um adapter específico."""
        adapters = self.list_adapters()
        for adapter in adapters:
            if adapter["adapter_id"] == adapter_id:
                return adapter
        return None
    
    def find_gap(self, capability: str) -> Optional[Dict[str, Any]]:
        """Identifica se existe adapter para uma capability."""
        adapters = self.list_adapters()
        capability_lower = capability.lower()
        
        for adapter in adapters:
            for cap in adapter.get("capabilities", []):
                if capability_lower in cap.lower():
                    return None
        
        return {
            "capability": capability,
            "missing_adapter": True,            "suggested_id": self._suggest_adapter_id(capability),
            "suggested_name": self._suggest_adapter_name(capability),
        }
    
    def _get_known_adapters(self) -> List[Dict[str, Any]]:
        """Lista de adapters conhecidos."""
        return [
            {
                "adapter_id": "llm_router",
                "name": "LLM Router",
                "description": "Roteamento dinâmico de LLMs",
                "capabilities": ["code_generation", "self_repair", "planning"],
                "config_keys": ["default_provider", "fallback_enabled"],
                "example_yaml": "llm_router:\n  id: \"llm_router\"\n  config:\n    task_type: \"code_generation\"\n",
            },
            {
                "adapter_id": "github_worker",
                "name": "GitHub Worker",
                "description": "Operações no GitHub",
                "capabilities": ["create_pull_request", "create_issue", "push_commits"],
                "config_keys": ["github_token", "repo_name"],
                "example_yaml": "github_worker:\n  id: \"github_worker\"\n  config:\n    action: \"create_pull_request\"\n",
            },
            {
                "adapter_id": "persistent_shell_adapter",
                "name": "Persistent Shell",
                "description": "Terminal stateful",
                "capabilities": ["run_shell_command", "run_tests", "browse_directory"],
                "config_keys": ["timeout_seconds", "working_dir"],
                "example_yaml": "persistent_shell_adapter:\n  id: \"persistent_shell_adapter\"\n  config:\n    action: \"run_command\"\n",
            },
            {
                "adapter_id": "telegram_adapter",
                "name": "Telegram Adapter",
                "description": "Interface via Telegram",
                "capabilities": ["send_message", "send_voice", "receive_message"],
                "config_keys": ["telegram_token", "chat_id"],
                "example_yaml": "telegram_adapter:\n  id: \"telegram_adapter\"\n  config:\n    action: \"send_message\"\n",
            },
            {
                "adapter_id": "consolidated_context_service",
                "name": "Consolidated Context",
                "description": "Snapshot do código",
                "capabilities": ["read_context", "refresh_context"],
                "config_keys": ["consolidated_path"],
                "example_yaml": "consolidated_context_service:\n  id: \"consolidated_context_service\"\n  config:\n    action: \"read\"\n",
            },
            {
                "adapter_id": "capability_manager",
                "name": "Capability Manager",                "description": "Gerenciamento de capabilities",
                "capabilities": ["list_capabilities", "execute_capability"],
                "config_keys": [],
                "example_yaml": "capability_manager:\n  id: \"capability_manager\"\n  config:\n    action: \"list_capabilities\"\n",
            },
            {
                "adapter_id": "procedural_memory",
                "name": "Procedural Memory",
                "description": "Memória de padrões",
                "capabilities": ["store_pattern", "find_similar"],
                "config_keys": [],
                "example_yaml": "procedural_memory:\n  id: \"procedural_memory\"\n  config:\n    action: \"store_pattern\"\n",
            },
            {
                "adapter_id": "semantic_memory",
                "name": "Semantic Memory",
                "description": "Memória de eventos",
                "capabilities": ["store_event", "query_similar"],
                "config_keys": [],
                "example_yaml": "semantic_memory:\n  id: \"semantic_memory\"\n  config:\n    action: \"query_similar\"\n",
            },
        ]
    
    def _discover_adapters(self) -> List[Dict[str, Any]]:
        """Descobre adapters registrados no Nexus."""
        discovered = []
        try:
            registry_path = Path("data/nexus_registry.jrvs")
            if registry_path.exists():
                from app.utils.document_store import document_store
                registry = document_store.read(registry_path)
                components = registry.get("components", {})
                for comp_id, comp_info in components.items():
                    hint_path = comp_info.get("hint_path", "")
                    if "adapter" in hint_path.lower() or "worker" in hint_path.lower():
                        discovered.append({
                            "adapter_id": comp_id,
                            "name": comp_id.replace("_", " ").title(),
                            "description": f"Componente: {hint_path}",
                            "capabilities": ["execute"],
                            "config_keys": [],
                            "example_yaml": f"{comp_id}:\n  id: \"{comp_id}\"\n",
                        })
        except Exception as e:
            logger.debug(f"[AdapterRegistry] Erro ao descobrir: {e}")
        return discovered
    
    def _suggest_adapter_id(self, capability: str) -> str:
        import re
        name = capability.lower()        name = re.sub(r"[^a-z0-9]", "_", name)
        return f"{name}_adapter"
    
    def _suggest_adapter_name(self, capability: str) -> str:
        return capability.title() + " Adapter"
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True