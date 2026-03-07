
# -*- coding: utf-8 -*-
"""Telegram Adapter — Interface de voz/texto via Telegram.

Integrado com FineTuneDatasetCollector para coleta automática de dados.
Suporta pipeline de backup via action: upload_backup.
"""
import logging
import os
from typing import Optional, Dict, Any, Callable
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

class TelegramAdapter(NexusComponent):
    """Adapter para bot do Telegram."""

    def __init__(self):
        super().__init__()
        # Fallback para variáveis de ambiente
        self._bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        self._chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        self._finetune_collector = None

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """NexusComponent entry-point — suporta backup de arquivo via pipeline.
        
        Ações suportadas:
        - "upload_backup": envia CORE_LOGIC_CONSOLIDATED.txt via Telegram
        - "configure": {telegram_bot_token, chat_id}
        - "process_message": {message}
        - "send_message": {chat_id, text}
        - "send_document": {chat_id, file_path, caption}
        - "start_polling": {}
        """
        # 1. Extrair config do contexto (para pipelines)
        config = context.get("config", {})
        action = config.get("action") or context.get("action", "")
        
        # 2. Atualizar credenciais se vierem do config do pipeline
        if config.get("token"):
            self._bot_token = config["token"]
        if config.get("chat_id"):
            self._chat_id = config["chat_id"]
        
        # 3. Resolver collector para fine-tuning (lazy)
        if self._finetune_collector is None:
            self._finetune_collector = nexus.resolve("finetune_dataset_collector")

        # =========================================================
        # AÇÃO: upload_backup (usada pelo pipeline sync_drive.yml)
        # =========================================================
        if action == "upload_backup":
            return self._action_upload_backup(context)

        # =========================================================
        # AÇÃO: send_document (upload genérico de arquivo)
        # =========================================================
        elif action == "send_document":
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

        # =========================================================
        # AÇÕES: chat/mensagens
        # =========================================================
        elif action == "configure":
            self._bot_token = config.get("telegram_bot_token") or self._bot_token
            self._chat_id = config.get("chat_id") or self._chat_id
            return {"success": True, "configured": bool(self._bot_token and self._chat_id)}

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
            callback = context.get("callback")
            logger.info("[TelegramAdapter] Polling iniciado (modo webhook).")
            return {"success": True, "mode": "webhook"}

        return {"success": False, "error": f"Ação desconhecida: {action}"}

    def _action_upload_backup(self, context: dict) -> dict:
        """Pipeline action: upload do consolidado via Telegram.
        
        Busca file_path em:
        1. context["result"]["file_path"]
        2. context["artifacts"]["consolidator"]["file_path"]
        3. context["artifacts"]["consolidator"] (string direta)
        """
        logger.info("📤 [TELEGRAM] Executando ação de backup.")
        
        # Buscar file_path com fallbacks
        res_data = context.get("result", {})
        file_path = res_data.get("file_path") if isinstance(res_data, dict) else None
        
        if not file_path:
            cons_art = context.get("artifacts", {}).get("consolidator", {})
            if isinstance(cons_art, dict):
                file_path = cons_art.get("file_path")
            elif isinstance(cons_art, str):
                file_path = cons_art
        
        if not file_path:
            logger.warning("[TELEGRAM] Arquivo de backup não localizado no contexto.")
            return context
        
        if not os.path.exists(file_path):
            logger.error(f"[TELEGRAM] Arquivo não encontrado: {file_path}")
            return context
        
        # Enviar via send_document (reusa lógica de upload)
        try:
            result = self.execute({
                "action": "send_document",
                "chat_id": self._chat_id,
                "file_path": file_path,
                "caption": "🤖 Jarvis — Backup de DNA"
            })
            if result.get("success"):
                logger.info("✅ [TELEGRAM] Backup enviado com sucesso.")
            else:
                logger.error(f"❌ [TELEGRAM] Falha no envio: {result.get('error')}")
        except Exception as e:
            logger.error(f"💥 [TELEGRAM] Erro no upload de documento: {e}")
        
        return context

    def configure(self, config: dict):
        """Configura token e chat_id do bot."""
        self._bot_token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_TOKEN") or self._bot_token
        self._chat_id = config.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID") or self._chat_id
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

    async def send_document(self, chat_id: str, file_path: str, caption: str = "📦 Backup"):
        """Envia documento para usuário no Telegram (assíncrono)."""
        if not self._bot_token:
            logger.warning("[TelegramAdapter] Bot token não configurado")
            return

        if not os.path.exists(file_path):
            logger.error(f"[TelegramAdapter] Arquivo não encontrado: {file_path}")
            return

        import aiohttp
        url = f"https://api.telegram.org/bot{self._bot_token}/sendDocument"
        
        try:
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
                            logger.info(f"[TelegramAdapter] Documento enviado: {file_path}")
                            return result
                        else:
                            error_text = await resp.text()
                            logger.error(f"[TelegramAdapter] Falha: {resp.status} — {error_text}")
        except Exception as e:
            logger.error(f"[TelegramAdapter] Erro ao enviar documento: {e}")

    # ------------------------------------------------------------------
    # Métodos de polling (stub para compatibilidade)
    # ------------------------------------------------------------------

    def start_polling(self, callback: Optional[Callable] = None):
        """Inicia polling do Telegram (modo webhook)."""
        logger.info("[TelegramAdapter] Polling iniciado (modo webhook).")
        if callback:
            logger.debug("[TelegramAdapter] Callback registrado para modo polling futuro.")
        return {"success": True, "mode": "webhook"}

    def stop_polling(self):
        """Para polling do Telegram."""
        logger.info("[TelegramAdapter] Polling parado.")
        return {"success": True}