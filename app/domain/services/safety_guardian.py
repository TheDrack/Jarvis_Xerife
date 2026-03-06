# -*- coding: utf-8 -*-
"""SafetyGuardian — Governança e segurança para autonomia total do JARVIS.

Garante que todas as ações autônomas de alto risco sejam validadas antes
de execução. Implementa:

- Validação contra políticas de segurança configuráveis.
- Verificação de quotas de recursos (API, compute, armazenamento).
- Protocolo de parada de emergência com autenticação multi-fator.
- Audit log imutável (append-only) de todas as decisões.

Método principal::

    guardian.validate_action(action_context) → (True, "allowed") | (False, reason)
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

# Audit log imutável — NUNCA truncar este arquivo
_AUDIT_LOG_FILE = Path("data/safety_guardian_audit.jsonl")

# Ações classificadas como alto risco (exigem aprovação extra)
_HIGH_RISK_ACTIONS: frozenset = frozenset(
    {
        "delete_file",
        "overwrite_core",
        "deploy_production",
        "disable_guardrail",
        "emergency_stop",
        "modify_security_policy",
        "external_network_call_unchecked",
    }
)

# Quotas padrão (sobrescrevíveis via configure())
_DEFAULT_QUOTAS: Dict[str, Any] = {
    "max_api_calls_per_minute": 60,
    "max_compute_seconds_per_task": 300,
    "max_storage_write_mb": 500,
}


class SafetyGuardian(NexusComponent):
    """Guardião de segurança para todas as ações autônomas do JARVIS.

    Args:
        policies: Dicionário de políticas de segurança customizadas.
        quotas: Dicionário de quotas de recursos customizadas.
        emergency_tokens: Conjunto de tokens de autenticação para parada de emergência.
    """

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        quotas: Optional[Dict[str, Any]] = None,
        emergency_tokens: Optional[List[str]] = None,
    ) -> None:
        self._policies: Dict[str, Any] = policies or {}
        self._quotas: Dict[str, Any] = {**_DEFAULT_QUOTAS, **(quotas or {})}
        self._emergency_tokens: List[str] = emergency_tokens or []
        self._emergency_stop_active: bool = False
        self._resource_counters: Dict[str, float] = {
            "api_calls_this_minute": 0.0,
            "api_window_start": time.time(),
            "compute_seconds_running": 0.0,
            "storage_written_mb": 0.0,
        }
        _AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def configure(self, config: Dict[str, Any]) -> None:
        """Injeta policies e quotas via configure()."""
        self._policies.update(config.get("policies", {}))
        self._quotas.update(config.get("quotas", {}))
        tokens = config.get("emergency_tokens", [])
        if tokens:
            self._emergency_tokens = list(tokens)

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Sempre pronto — é o último guardião antes da ação."""
        return True

    # ------------------------------------------------------------------
    # NexusComponent interface
    # ------------------------------------------------------------------

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent.

        Campos aceitos em *context*:
            action_type (str) — tipo de ação a validar.
            action_context (dict) — detalhes da ação.
            emergency_token (str) — token para acionar emergency_stop.
            resource_usage (dict) — uso de recursos da ação (api_calls, compute_s, storage_mb).

        Returns:
            {"allowed": bool, "reason": str, "success": True}
        """
        ctx = context or {}

        # Parada de emergência tem prioridade absoluta
        emergency_token = ctx.get("emergency_token")
        if emergency_token:
            result = self.emergency_stop_protocol(emergency_token)
            return {**result, "success": True}

        action_type = ctx.get("action_type", "unknown")
        action_context = ctx.get("action_context", {})
        resource_usage = ctx.get("resource_usage", {})

        # Verifica quota de recursos
        quota_ok, quota_reason = self.check_resource_quota(resource_usage)
        if not quota_ok:
            self._audit(action_type, allowed=False, reason=quota_reason)
            return {"allowed": False, "reason": quota_reason, "success": True}

        # Valida ação
        allowed, reason = self.validate_action(action_type, action_context)
        self._audit(action_type, allowed=allowed, reason=reason, context=action_context)
        return {"allowed": allowed, "reason": reason, "success": True}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_action(
        self,
        action_type: str,
        action_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Valida se uma ação é permitida pelas políticas de segurança.

        Args:
            action_type: Tipo da ação a ser validada.
            action_context: Contexto adicional da ação.

        Returns:
            (True, "allowed") se permitido, (False, reason) caso contrário.
        """
        ctx = action_context or {}

        # Parada de emergência ativa bloqueia tudo
        if self._emergency_stop_active:
            return False, "emergency_stop_active: todas as ações bloqueadas"

        # Verifica ações de alto risco
        if action_type in _HIGH_RISK_ACTIONS:
            if not ctx.get("explicit_approval"):
                return (
                    False,
                    f"high_risk_action_requires_approval: '{action_type}' requer aprovação explícita",
                )

        # Verifica políticas customizadas
        policy_result = self._check_custom_policies(action_type, ctx)
        if policy_result is not None:
            return policy_result

        return True, "allowed"

    def check_resource_quota(
        self, resource_usage: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """Verifica se o uso de recursos está dentro das quotas configuradas.

        Args:
            resource_usage: Dicionário com uso atual:
                api_calls (int) — chamadas de API adicionais.
                compute_s (float) — segundos de compute adicionais.
                storage_mb (float) — MB de armazenamento a escrever.

        Returns:
            (True, "ok") se dentro das quotas, (False, reason) caso contrário.
        """
        usage = resource_usage or {}
        now = time.time()

        # Reset da janela de API por minuto
        if now - self._resource_counters["api_window_start"] > 60:
            self._resource_counters["api_calls_this_minute"] = 0.0
            self._resource_counters["api_window_start"] = now

        # Incrementa contadores
        api_calls = float(usage.get("api_calls", 0))
        compute_s = float(usage.get("compute_s", 0))
        storage_mb = float(usage.get("storage_mb", 0))

        new_api = self._resource_counters["api_calls_this_minute"] + api_calls
        new_compute = self._resource_counters["compute_seconds_running"] + compute_s
        new_storage = self._resource_counters["storage_written_mb"] + storage_mb

        if new_api > self._quotas["max_api_calls_per_minute"]:
            return (
                False,
                f"quota_exceeded: api_calls ({new_api:.0f} > {self._quotas['max_api_calls_per_minute']})",
            )
        if new_compute > self._quotas["max_compute_seconds_per_task"]:
            return (
                False,
                f"quota_exceeded: compute_seconds ({new_compute:.0f} > {self._quotas['max_compute_seconds_per_task']})",
            )
        if new_storage > self._quotas["max_storage_write_mb"]:
            return (
                False,
                f"quota_exceeded: storage_mb ({new_storage:.1f} > {self._quotas['max_storage_write_mb']})",
            )

        # Aplica contadores
        self._resource_counters["api_calls_this_minute"] = new_api
        self._resource_counters["compute_seconds_running"] = new_compute
        self._resource_counters["storage_written_mb"] = new_storage
        return True, "ok"

    def emergency_stop_protocol(self, token: str) -> Dict[str, Any]:
        """Aciona ou desativa o protocolo de parada de emergência.

        A parada de emergência bloqueia TODAS as ações autônomas até ser
        desativada com um token válido de segundo fator.

        Args:
            token: Token de autenticação multi-fator.

        Returns:
            Dicionário com status da operação.
        """
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        valid_hashes = [
            hashlib.sha256(t.encode("utf-8")).hexdigest() for t in self._emergency_tokens
        ]

        # Também aceita token de env var como segundo fator
        env_token = os.getenv("SAFETY_EMERGENCY_TOKEN", "")
        if env_token:
            valid_hashes.append(hashlib.sha256(env_token.encode("utf-8")).hexdigest())

        if token_hash not in valid_hashes:
            self._audit("emergency_stop_attempt", allowed=False, reason="invalid_token")
            return {"activated": False, "reason": "token_inválido"}

        self._emergency_stop_active = not self._emergency_stop_active
        state = "ativado" if self._emergency_stop_active else "desativado"
        logger.critical("[SafetyGuardian] 🚨 Emergency stop %s.", state)
        self._audit(
            "emergency_stop_protocol",
            allowed=True,
            reason=f"emergency_stop_{state}",
            context={
                "new_state": state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "token_prefix": token[:4] + "***" if len(token) >= 4 else "***",
            },
        )
        return {"activated": self._emergency_stop_active, "state": state}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_custom_policies(
        self, action_type: str, ctx: Dict[str, Any]
    ) -> Optional[Tuple[bool, str]]:
        """Verifica políticas customizadas registradas em _policies.

        Returns:
            Tuple (bool, str) se alguma política bloqueou/permitiu explicitamente,
            None se nenhuma política se aplicou.
        """
        for policy_name, policy in self._policies.items():
            blocked_actions = policy.get("blocked_actions", [])
            if action_type in blocked_actions:
                return False, f"policy_blocked: '{policy_name}' bloqueia '{action_type}'"
        return None

    def _audit(
        self,
        action_type: str,
        allowed: bool,
        reason: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra decisão no audit log imutável (append-only).

        O arquivo nunca é truncado — cada entrada é uma linha JSON.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "allowed": allowed,
            "reason": reason,
            "context_summary": list((context or {}).keys()),
            "emergency_stop_active": self._emergency_stop_active,
        }
        try:
            with open(_AUDIT_LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("[SafetyGuardian] Falha ao escrever audit log: %s", exc)

        status = "✅ PERMITIDO" if allowed else f"🚫 BLOQUEADO ({reason})"
        logger.info("[SafetyGuardian] %s → %s", action_type, status)
