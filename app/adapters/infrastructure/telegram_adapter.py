
# -*- coding: utf-8 -*-
"""Telegram Adapter — Interface de voz/texto via Telegram.

Integrado com FineTuneDatasetCollector para coleta automática de dados.
"""
import logging
from typing import Optional, Dict, Any
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    """Adapter para bot do Telegram."""

    def __init__(self):
        super().__init__()
        self._bot_token = None
        self._finetune_collector = None
        self._polling_task = None

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """NexusComponent entry-point."""
        action = context.get("action", "")

        if action == "configure":
            config = context.get("config", {})
            self._bot_token = config.get("telegram_bot_token")
            self._finetune_collector = nexus.resolve("finetune_dataset_collector")
            return {"success": True, "configured": bool(self._bot_token)}

        elif action == "process_message":
            message = context.get("message", {})
            return {"success": True, "message_received": message.get("text", "")}

        elif action == "send_message":
            chat_id = context.get("chat_id")
            text = context.get("text")
            if self._bot_token and chat_id and text:
                return {"success": True, "queued": True, "chat_id": chat_id}
            return {"success": False, "error": "Token, chat_id ou texto ausente"}

        elif action == "start_polling":
            # Polling é gerenciado externamente via webhook
            return {"success": True, "polling": "webhook_mode"}

        return {"success": False, "error": f"Ação desconhecida: {action}"}

    def configure(self, config: dict):
        """Configura token do bot."""
        self._bot_token = config.get("telegram_bot_token")
        self._finetune_collector = nexus.resolve("finetune_dataset_collector")

    async def process_message(self, message: dict) -> Dict[str, Any]:
        """Processa mensagem do Telegram e registra para treino."""
        user_id = message.get("from", {}).get("id", "unknown")
        raw_message = message.get("text", "")

        assistant = nexus.resolve("assistant_service")
        if assistant is None:
            return {"success": False, "error": "AssistantService indisponível"}

        try:
            response = await assistant.execute({
                "user_input": raw_message,
                "user_id": str(user_id),
                "source": "telegram"
            })

            bot_reply = response.get("response", "Comando processado")
            success = response.get("success", False)

            if self._finetune_collector is not None:
                self._finetune_collector.collect_from_interaction(
                    user_id=str(user_id),
                    prompt=raw_message,
                    completion=bot_reply,
                    outcome="executed" if success else "clarified",
                    source="telegram",
                    feedback=None
                )

            return {"success": True, "response": bot_reply}

        except Exception as e:
            logger.error("[TelegramAdapter] Erro: %s", e)
            if self._finetune_collector is not None:
                self._finetune_collector.collect_from_interaction(
                    user_id=str(user_id),
                    prompt=raw_message,
                    completion=str(e),
                    outcome="rejected",
                    source="telegram",
                    feedback=None
                )
            return {"success": False, "error": str(e)}

    async def send_message(self, chat_id: str, text: str):
        """Envia mensagem para usuário no Telegram."""
        if not self._bot_token:
            logger.warning("[TelegramAdapter] Bot token não configurado")
            return

        import aiohttp
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        logger.debug("[TelegramAdapter] Mensagem enviada para %s", chat_id)
                    else:
                        logger.warning("[TelegramAdapter] Falha ao enviar: %d", resp.status)
        except Exception as e:
            logger.error("[TelegramAdapter] Erro ao enviar: %s", e)

    # ------------------------------------------------------------------
    # ADIÇÃO: Métodos faltantes exigidos pelo main.py
    # ------------------------------------------------------------------

    def start_polling(self):
        """Inicia polling do Telegram (modo webhook — polling é gerenciado externamente).
        
        ADIÇÃO: Método stub para compatibilidade com bootstrap do main.py.
        """
        logger.info("[TelegramAdapter] Polling iniciado (modo webhook).")
        # Webhook é gerenciado pelo endpoint /v1/telegram/webhook no api_server.py
        # Não há loop de polling ativo neste adapter
        return {"success": True, "mode": "webhook"}

    def stop_polling(self):
        """Para polling do Telegram."""
        logger.info("[TelegramAdapter] Polling parado.")
        return {"success": True}