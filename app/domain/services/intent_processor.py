# -*- coding: utf-8 -*-
"""Intent Processor — Orquestra fluxo com checkpoint de hardware MacroDroid.
ATUALIZAÇÃO: Adicionado checkpoint de hardware (Passo 5 da integração).
"""
import logging
from typing import Any, Dict, Optional
from app.core.nexus import CloudMock, NexusComponent, nexus
from app.domain.models import CommandType

logger = logging.getLogger(__name__)


class IntentProcessor(NexusComponent):
    """
    Processador de Intenções com checkpoint de hardware MacroDroid.
    
    Fluxo Atualizado:
    1. Entrada do Usuário
    2. → Verificador de Comando de Dispositivo (NOVO - Passo 5)
    3. → Se for comando: Executa MacroDroid e Retorna Sucesso
    4. → Se não for: Envia para LLM (fluxo original)
    """
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return True
    
    def execute(self, context: Dict[str, Any]) -> Any:
        """
        Processa intenção com checkpoint de hardware.
        
        Args:
            context: Dict com chave 'intent' (objeto Intent)
            
        Returns:
            String com resposta ou resultado da execução
        """
        if not context:
            return "Erro: Contexto inválido ou vazio."
        
        intent_obj = context.get("intent")
        if not intent_obj:
            return "Erro: Objeto de intenção não encontrado no contexto."
        
        # 1. Identificação do Tipo de Comando
        cmd_type = getattr(intent_obj, 'command_type', CommandType.UNKNOWN)
        
        if hasattr(cmd_type, 'name'):
            target_id = cmd_type.name.lower()
        else:            target_id = str(cmd_type).split('.')[-1].lower()
        
        raw_text = getattr(intent_obj, 'raw_input', str(intent_obj))
        
        # 2. FILTRO DE ATALHO: Se for unknown, verifica hardware ANTES de LLM
        if target_id == "unknown":
            logger.info("🤖 [PROCESSOR] Intenção desconhecida. Verificando hardware...")
            
            # ← PASSO 5: Checkpoint de Hardware MacroDroid
            hardware_result = self._check_hardware_command(raw_text)
            if hardware_result.get("success"):
                logger.info("✅ [PROCESSOR] Comando de hardware executado")
                return hardware_result.get("message", "Comando executado")
            
            # Não é comando de hardware → LLM (fluxo original)
            logger.info("🔍 [PROCESSOR] Não é hardware. Delegando para LLM.")
            return self._process_with_llm(raw_text)
        
        # 3. RESOLUÇÃO DE COMANDO TÉCNICO (fluxo original)
        logger.info(f"🎯 [PROCESSOR] Buscando executor para: '{target_id}'")
        executor = nexus.resolve(target_id)
        
        if executor and not isinstance(executor, CloudMock):
            try:
                params = getattr(intent_obj, 'parameters', {})
                if not isinstance(params, dict):
                    params = {"data": params}
                
                result = executor.execute(params)
                
                if isinstance(result, dict):
                    return result.get("message", "Comando executado com sucesso.")
                return str(result)
                
            except Exception as e:
                logger.error(f"💥 [PROCESSOR] Erro ao executar {target_id}: {e}")
                return f"Erro ao executar comando: {e}"
        
        # 4. FALLBACK FINAL (fluxo original)
        logger.warning(f"⚠️ [PROCESSOR] Executor '{target_id}' não encontrado. Fallback LLM.")
        return self._process_with_llm(raw_text)
    
    def _check_hardware_command(self, user_input: str) -> Dict[str, Any]:
        """
        PASSO 5: Verifica se entrada é comando de hardware MacroDroid.
        
        Fluxo:
        1. Usa DeviceIntentTranslator para detectar comando
        2. Se for comando, usa MacroDroidAdapter para executar
        3. Retorna resultado imediato (sem passar por LLM)        
        Args:
            user_input: Texto bruto do usuário
            
        Returns:
            Dict com success, message, action
        """
        try:
            # Resolve tradutor via Nexus
            translator = nexus.resolve("device_intent_translator")
            if not translator or isinstance(translator, CloudMock):
                logger.debug("[PROCESSOR] DeviceIntentTranslator indisponível")
                return {"success": False}
            
            # Traduz entrada do usuário
            translation = translator.translate(user_input)
            
            if not translation.get("is_device_command"):
                logger.debug(f"[PROCESSOR] Não é comando de hardware: {user_input}")
                return {"success": False}
            
            # É comando de hardware → Executa via MacroDroid
            logger.info(f"📱 [PROCESSOR] Comando de hardware detectado: {translation.get('action')}")
            
            macrodroid = nexus.resolve("macrodroid_adapter")
            if not macrodroid or isinstance(macrodroid, CloudMock):
                logger.warning("[PROCESSOR] MacroDroidAdapter indisponível")
                return {
                    "success": False,
                    "message": "MacroDroid não configurado. Configure MACRODROID_DEVICE_ID e MACRODROID_API_KEY."
                }
            
            # Executa comando
            result = macrodroid.execute({
                "action": translation.get("action"),
                "params": {
                    "data": translation.get("data"),
                    "timeout": 5
                }
            })
            
            return result
            
        except Exception as e:
            logger.error(f"[PROCESSOR] Erro no checkpoint de hardware: {e}")
            return {"success": False, "message": f"Erro de hardware: {e}"}
    
    def _process_with_llm(self, text: str) -> str:
        """
        Delegação para LLM (fluxo original mantido).        
        Args:
            text: Texto bruto do usuário
            
        Returns:
            Resposta do LLM ou mensagem de fallback
        """
        try:
            # Tenta resolver LLM service via Nexus
            llm = nexus.resolve("llm_service")
            if llm and not isinstance(llm, CloudMock):
                return llm.chat(text)
            
            # Fallback: AIGateway
            ai_gateway = nexus.resolve("ai_gateway")
            if ai_gateway and not isinstance(ai_gateway, CloudMock):
                result = ai_gateway.execute({"messages": [{"role": "user", "content": text}]})
                if isinstance(result, dict):
                    return result.get("response", "Não entendi o comando.")
                return str(result)
                
        except Exception as e:
            logger.debug(f"[PROCESSOR] LLM fallback falhou: {e}")
        
        return "Comando não reconhecido. Tente ser mais específico."


# Compatibilidade com código legado
IntentHandler = IntentProcessor