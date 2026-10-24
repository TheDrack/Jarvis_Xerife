"""Adaptador opcional para o cliente Google ARTEMIS.

A dependência artemis-client é carregada somente quando necessária. O adaptador
não inicializa ADB, instala software no telefone, nem seleciona dispositivo
implicitamente. A criação do cliente é injetável para testes.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from app.application.ports.android_navigation import AndroidNavigationPort

logger = logging.getLogger(__name__)


class ArtemisAndroidNavigationAdapter(AndroidNavigationPort):
    """Ponte modular Jarvis -> ARTEMIS Python SDK."""

    VALID_PROFILES = {"flash", "pro"}

    def __init__(
        self,
        server_url: Optional[str] = None,
        client_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.server_url = (server_url or "").strip().rstrip("/")
        self._client_factory = client_factory
        self._clients: Dict[str, Any] = {}

    def _get_client(self, device_id: str) -> Any:
        if not device_id or not device_id.strip():
            raise ValueError("device_id é obrigatório; seleção automática está desativada.")
        if not self.server_url:
            raise RuntimeError("Configure JARVIS_ARTEMIS_SERVER_URL com a URL do servidor ARTEMIS.")
        if device_id not in self._clients:
            factory = self._client_factory
            if factory is None:
                try:
                    from artemis_client import ArtemisClient
                except ImportError as exc:
                    raise RuntimeError(
                        "Cliente ARTEMIS ausente. Instale o pacote artemis-client "
                        "em um ambiente isolado antes de habilitar a integração."
                    ) from exc
                factory = ArtemisClient
            self._clients[device_id] = factory(
                self.server_url, device_serial=device_id, default_profile="pro"
            )
        return self._clients[device_id]

    def run_task(
        self,
        instruction: str,
        device_id: str,
        profile: str = "pro",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        instruction = (instruction or "").strip()
        if not instruction:
            return {"success": False, "status": "invalid_instruction", "error": "instruction é obrigatória"}
        if profile not in self.VALID_PROFILES:
            return {"success": False, "status": "invalid_profile", "error": "profile deve ser 'flash' ou 'pro'"}
        try:
            client = self._get_client(device_id)
            result = client.run(instruction, profile=profile)
            succeeded = bool(getattr(result, "succeeded", False))
            return {
                "success": succeeded,
                "status": str(getattr(result, "status", "succeeded" if succeeded else "failed")),
                "device_id": device_id,
                "profile": profile,
                "trace_id": getattr(result, "trace_id", None),
                "error": getattr(result, "error", None),
                "result": result.model_dump() if callable(getattr(result, "model_dump", None)) else str(result),
            }
        except (RuntimeError, ValueError) as exc:
            return {"success": False, "status": "configuration_error", "device_id": device_id, "error": str(exc)}
        except Exception as exc:
            logger.exception("ARTEMIS Android task failed for device %s", device_id)
            return {"success": False, "status": "error", "device_id": device_id, "error": str(exc)}
