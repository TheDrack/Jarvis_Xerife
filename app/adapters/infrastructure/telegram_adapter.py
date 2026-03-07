
# -*- coding: utf-8 -*-
"""Telegram Adapter — Interface de voz/texto via Telegram.

Integrado com FineTuneDatasetCollector para coleta automática de dados.
"""
import logging
import os
from typing import Optional, Dict, Any
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    """Adapter para bot do Telegram."""

    def __init__(self):
        super().__init__()
        self._bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self._chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
        self._finetune_collector = None

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """NexusComponent entry-point — suporta backup de arquivo via Telegram.
        
        Ações suportadas:
        - "configure": {telegram_bot_token, chat_id}
        - "process_message": {message}
        - "send_message": {chat_id, text}
        - "send_document": {chat_id, file_path, caption}  ← ADIÇÃO PARA BACKUP
        - "start_polling": {}
        """
        action = context.get("action", "")

        if action == "configure":
            config = context.get("config", {})
            self._bot_token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
            self._chat_id = config.get("chat_id") or os.getenv("TELEGRAM_ADMIN_CHAT_ID")
            self._finetune_collector = nexus.resolve("finetune_dataset_collector")
            return {"success": True, "configured": bool(self._bot_token and self._chat_id)}

        elif action == "send_document":
            # ← ADIÇÃO CRÍTICA: Suporte a upload de arquivo para backup
            chat_id = context.get("chat_id") or self._chat_id
            file_path = context.get("file_path")
            caption = context.get("caption", "📦 Backup do Jarvis")
            
            if not self._bot_token or not chat_id or not file_path:
                logger.warning("[TelegramAdapter] send_document: parâmetros ausentes")
                return {"success": False, "error": "Token, chat_id ou file_path ausente"}
            
            if not os.path.exists(file_path):
                logger.error(f"[TelegramAdapter] Arquivo não encontrado: {file_path}")
                return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}
            
            try:
                import aiohttp
                url = f"https://api.telegram.org/bot{self._bot_token}/sendDocument"
                
                with open(file_path, "rb") as f:
                    form = aiohttp.FormData()
                    form.add_field("chat_id", chat_id)
                    form.add_field("document", f, filename=os.path.basename(file_path))
                    if caption:
                        form.add_field("caption", caption)
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, data=form) as resp:
                            if resp.status == 200:
                                result = await resp.json()
                                logger.info(f"[TelegramAdapter] Backup enviado: {file_path}")
                                return {"success": True, "message_id": result.get("result", {}).get("message_id")}
                            else:
                                error_text = await resp.text()
                                logger.error(f"[TelegramAdapter] Falha no upload: {resp.status} — {error_text}")
                                return {"success": False, "error": f"HTTP {resp.status}: {error_text}"}
                                
            except Exception as e:
                logger.error(f"[TelegramAdapter] Erro ao enviar documento: {e}")
                return {"success": False, "error": str(e)}

        elif action == "process_message":
            message = context.get("message", {})
            return {"success": True, "message_received": message.get("text", "")}

        elif action == "send_message":
            chat_id = context.get("chat_id") or self._chat_id
            text = context.get("text")
            if self._bot_token and chat_id and text:
                return {"success": True, "queued": True, "chat_id": chat_id}
            return {"success": False, "error": "Token, chat_id ou texto ausente"}

        elif action == "start_polling":
            callback = context.get("callback")  # Aceita callback opcional
            logger.info("[TelegramAdapter] Polling iniciado (modo webhook).")
            return {"success": True, "mode": "webhook"}

        return {"success": False, "error": f"Ação desconhecida: {action}"}

    def configure(self, config: dict):
        """Configura token e chat_id do bot."""
        self._bot_token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
        self._chat_id = config.get("chat_id") or os.getenv("TELEGRAM_ADMIN_CHAT_ID")
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
        """Envia mensagem de texto para usuário no Telegram."""
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
    # Métodos de polling (stub para compatibilidade)
    # ------------------------------------------------------------------

    def start_polling(self, callback: Optional[callable] = None):
        """Inicia polling do Telegram (modo webhook)."""
        logger.info("[TelegramAdapter] Polling iniciado (modo webhook).")
        if callback:
            logger.debug("[TelegramAdapter] Callback registrado para modo polling futuro.")
        return {"success": True, "mode": "webhook"}

    def stop_polling(self):
        """Para polling do Telegram."""
        logger.info("[TelegramAdapter] Polling parado.")
        return {"success": True}