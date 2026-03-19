# -*- coding: utf-8 -*-
"""Capability Authorizer - Security layer for capability execution.
CORREÇÃO: Scan recursivo de payload e conformidade com Nexus.
"""
import logging
import re
from typing import Any, Dict, Optional, Set, Union
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

# Padrões expandidos para cobrir vetores de injeção
_INJECTION_PATTERNS = [
    re.compile(r"[;&|`]"),                     # Metacaracteres de shell (removido $ isolado)
    re.compile(r"\.\./"),                      # Path traversal
    re.compile(r"<\s*\("),                     # Process substitution
    re.compile(r"\$\(.*\)"),                   # Command substitution
    re.compile(r"\$\{[^}]+\}"),                # Variable expansion
    re.compile(r"`[^`]+`"),                    # Backtick execution
    re.compile(r"\b(eval|exec|system|popen|subprocess|os\.system)\b", re.IGNORECASE),
    re.compile(r"\b(rm\s+-rf|chmod|chown|sudo|su\s+)\b", re.IGNORECASE),
    re.compile(r"\\x[0-9a-f]{2}", re.IGNORECASE),  # Hex escapes
    re.compile(r"\\u[0-9a-f]{4}", re.IGNORECASE),  # Unicode escapes
    re.compile(r"%00"),                        # Null byte injection
]

# Capabilities que exigem confirmação humana explícita
_SENSITIVE_CAPABILITIES: Set[str] = {
    "system_executor",
    "auto_evolution",
    "github_worker",
    "pyinstaller_builder",
    "drive_uploader",
    "gist_uploader",
    "delete_file",
    "format_disk",
    "osint_search",
    "evolution_orchestrator",
}

# Allowlist padrão de capabilities aprovadas
_DEFAULT_ALLOWLIST: Set[str] = {
    "assistant_service", "command_interpreter", "intent_processor",
    "memory_manager", "vector_memory_adapter", "notification_service",
    "telegram_adapter", "gemini_adapter", "gateway_llm_adapter",
    "sqlite_history_adapter", "vision_adapter", "field_vision",
    "thought_log_service", "strategist_service", "task_runner",
    "browser_manager", "github_worker", "system_executor",
    "auto_evolution", "audit_logger", "capability_authorizer",
    "pii_redactor", "env_secrets_provider", "osint_search",
    "eagle_osint_adapter", "evolution_orchestrator", "ollama_adapter",
    "cost_tracker_adapter", "procedural_memory_adapter",
    "capability_index_service", "capability_blueprint_service",
    "capability_gap_reporter", "capability_detectors", "overwatch_daemon",
}

class CapabilityAuthorizer(NexusComponent):
    """Camada de autorização que protege a execução de capacidades."""
    
    def __init__(
        self,
        allowlist: Optional[Set[str]] = None,
        require_confirmation_for: Optional[Set[str]] = None,
    ) -> None:
        super().__init__()
        self._allowlist: Set[str] = allowlist if allowlist is not None else set(_DEFAULT_ALLOWLIST)
        self._sensitive: Set[str] = (
            require_confirmation_for
            if require_confirmation_for is not None
            else set(_SENSITIVE_CAPABILITIES)
        )

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Verifica se o autorizador está operacional."""
        return True
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Autoriza uma execução descrita pelo contexto do Nexus."""
        ctx = context or {}
        user = ctx.get("user", "anonymous")
        capability_name = ctx.get("capability_name", "")
        payload = ctx.get("payload", {})
        
        if not capability_name:
            return {"success": False, "error": "Campo 'capability_name' obrigatório."}
        
        try:
            self.authorize(user, capability_name, payload)
            return {"success": True, "authorized": True, "capability": capability_name}
        except (PermissionError, ValueError) as exc:
            logger.error(f"[Authorizer] Bloqueio: {str(exc)}")
            return {"success": False, "authorized": False, "error": str(exc)}
    
    def authorize(
        self,
        user: str,
        capability_name: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Avalia permissões para o usuário e capacidade fornecidos."""
        payload = payload or {}
        
        # 1. Check Allowlist
        if capability_name not in self._allowlist:
            raise PermissionError(f"Capability '{capability_name}' não está na allowlist.")
        
        # 2. Block Unauthorized Remote
        if payload.get("remote", False) and not payload.get("remote_authorized", False):
            raise PermissionError(f"Execução remota de '{capability_name}' exige 'remote_authorized': true.")
        
        # 3. Sensitive Protection
        if capability_name in self._sensitive and not payload.get("human_confirmed", False):
            raise PermissionError(f"Capability sensível '{capability_name}' exige confirmação humana.")
        
        # 4. Deep Payload Injection Scan
        self._deep_scan_injection(capability_name, payload)
        
        logger.info(f"✅ [Authorizer] '{capability_name}' autorizada para '{user}'.")
        return True
    
    def _deep_scan_injection(self, capability_name: str, data: Any) -> None:
        """Varredura recursiva em busca de padrões de injeção em qualquer nível do payload."""
        if isinstance(data, str):
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(data):
                    raise ValueError(f"Injeção detectada em '{capability_name}': padrão '{pattern.pattern}'")
        
        elif isinstance(data, dict):
            for v in data.values():
                self._deep_scan_injection(capability_name, v)
        
        elif isinstance(data, list):
            for item in data:
                self._deep_scan_injection(capability_name, item)
    
    def add_to_allowlist(self, capability_name: str) -> None:
        self._allowlist.add(capability_name)
    
    def remove_from_allowlist(self, capability_name: str) -> None:
        self._allowlist.discard(capability_name)

    def is_allowed(self, capability_name: str) -> bool:
        return capability_name in self._allowlist
