# -*- coding: utf-8 -*-
import os
import logging
from typing import Any, Dict

from app.core.nexus import nexus, NexusComponent
from app.application.services.user_communication_service import (
    CommunicationPriority, UserCommunicationService, dispatch_to_mobile,
)

logger = logging.getLogger(__name__)

class NotificationService(NexusComponent):
    """
    Serviço inteligente para despacho de mensagens agnóstico à interface.
    """
    def __init__(self):
        # Lista de interfaces prioritárias que o Jarvis deve tentar usar
        self.interface_priority = ["telegram_adapter", "whatsapp_adapter", "discord_adapter"]
        self.user_communication = UserCommunicationService()

    def execute(self, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Implementação do contrato NexusComponent."""
        ctx = context or {}
        message = ctx.get("message", "🤖 **JARVIS Online**")
        sent = self.broadcast_startup(message)
        return {"success": sent, "sent": sent}

    def broadcast_startup(self, message: str = "🤖 **JARVIS Online**"):
        """
        Localiza a primeira interface disponível via Nexus e envia o status.
        """
        for interface_id in self.interface_priority:
            adapter = nexus.resolve(interface_id)
            
            if adapter and hasattr(adapter, "send_message"):
                chat_id = self._get_target_id(interface_id)
                if not chat_id:
                    continue
                
                try:
                    adapter.send_message(message, chat_id=chat_id)
                    logger.info(f"✅ Notificação enviada via {interface_id}")
                    return True # Sucesso, não precisa tentar as outras
                except Exception as e:
                    logger.error(f"⚠️ Falha ao enviar via {interface_id}: {e}")
        
        logger.warning("❌ Nenhuma interface disponível para envio de notificação.")
        return False

    def communicate_user(
        self, event_key: str, message: str,
        priority: CommunicationPriority = CommunicationPriority.NORMAL,
    ) -> Dict[str, Any]:
        """Deliver a grounded event to the paired phone using presence-aware policy.

        Presence is used only when a live service is registered; otherwise it is
        unknown and non-urgent messages are deferred rather than interrupting.
        """
        presence = "unknown"
        try:
            presence_service = nexus.resolve("presence_service")
            if presence_service is not None:
                snapshot = presence_service.evaluate()
                presence = getattr(getattr(snapshot, "state", None), "value", "unknown")
        except Exception as exc:
            logger.debug("Presence unavailable for communication policy (%s)", type(exc).__name__)
        return self.user_communication.communicate(
            event_key=event_key, message=message, priority=priority, presence=presence,
            dispatch=dispatch_to_mobile,
        )

    def _get_target_id(self, interface_id: str) -> str:
        """Busca o ID de destino correto baseado na interface."""
        if "telegram" in interface_id:
            return os.getenv("TELEGRAM_CHAT_ID")
        elif "whatsapp" in interface_id:
            return os.getenv("WHATSAPP_NUMBER")
        return os.getenv("ADMIN_ID")
