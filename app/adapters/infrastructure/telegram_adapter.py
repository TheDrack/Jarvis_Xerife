
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
    
    def configure(self, config: dict):
        """Configura token do bot."""
        self._bot_token = config.get("telegram_bot_token")
        self._finetune_collector = nexus.resolve("finetune_dataset_collector")
    
    async def process_message(self, message: dict) -> Dict[str, Any]:
        """Processa mensagem do Telegram e registra para treino."""
        user_id = message.get("from", {}).get("id", "unknown")
        raw_message = message.get("text", "")
        
        # Executa comando
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
            
            # ADIÇÃO: Registra para fine-tuning (não remove funcionalidade existente)
            if self._finetune_collector:
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
            
            # ADIÇÃO: Registra erro para fine-tuning também
            if self._finetune_collector:
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