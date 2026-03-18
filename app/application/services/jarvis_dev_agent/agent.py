# -*- coding: utf-8 -*-
import logging
import traceback
from typing import Dict, Any, List
from app.core.nexus import Nexus
from app.domain.models.thought_log import ThoughtLog

logger = logging.getLogger(__name__)

class JarvisDevAgent:
    """
    Agente de Desenvolvimento Autônomo.
    Responsável por analisar gaps, propor soluções e aplicar correções via SurgicalEdit.
    """

    def __init__(self, nexus: Nexus):
        self.nexus = nexus
        # CORREÇÃO: Inicialização protegida. A resolução ocorre no momento do uso 
        # para garantir que o Nexus já completou o ciclo de bootstrap.
        self._memory = None
        self._gateway = None

    @property
    def memory(self):
        if not self._memory:
            self._memory = self.nexus.resolve("working_memory")
        return self._memory

    @property
    def gateway(self):
        if not self._gateway:
            self._gateway = self.nexus.resolve("metabolism_core")
        return self._gateway

    async def analyze_and_fix(self, issue_description: str) -> Dict[str, Any]:
        """Ciclo principal de Pensamento -> Ação -> Verificação."""
        logger.info(f"[DevAgent] Analisando problema: {issue_description}")
        
        # 1. Registro do pensamento inicial
        thought = ThoughtLog(
            step="initial_analysis",
            thought=f"Detectado problema: {issue_description}. Iniciando varredura de código.",
            target_file="multiple"
        )
        await self.memory.add_event("thought", thought.dict())

        try:
            # 2. Descoberta de código (Code Discovery)
            discovery = self.nexus.resolve("code_discovery_service")
            relevant_files = await discovery.find_relevant_context(issue_description)

            # 3. Solicitação de solução ao MetabolismCore (LLM)
            # O prompt instrui o LLM a usar o SurgicalEditService
            proposal = await self.gateway.generate_fix_proposal(
                issue=issue_description,
                context=relevant_files
            )

            # 4. Execução das Ações
            results = []
            for action in proposal.get("actions", []):
                res = await self.execute_action(action)
                results.append(res)

            return {
                "success": all(r.get("success") for r in results),
                "actions_performed": results
            }

        except Exception as e:
            # CORREÇÃO: Linha 99 - Sincronização de erro com a WorkingMemory
            # Sem isso, o JARVIS entra em loop pois não "lembra" do erro técnico.
            error_trace = traceback.format_exc()
            logger.error(f"[DevAgent] Falha crítica no ciclo de reparo: {e}")
            
            await self.memory.add_event("error", {
                "exception": str(e),
                "traceback": error_trace,
                "context": "analyze_and_fix"
            })
            
            return {"success": False, "error": str(e)}

    async def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Executa uma ação específica (edit, shell, create)."""
        action_type = action.get("type")
        
        if action_type == "surgical_edit":
            editor = self.nexus.resolve("surgical_edit_service")
            return editor.apply_surgical_edit(
                file_path=action["file"],
                search_block=action["search"],
                replace_block=action["replace"]
            )
        
        elif action_type == "shell_command":
            shell = self.nexus.resolve("persistent_shell_adapter")
            return await shell.execute(action["command"])

        return {"success": False, "error": f"Tipo de ação '{action_type}' não suportado."}
