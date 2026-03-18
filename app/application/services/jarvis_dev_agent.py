# -*- coding: utf-8 -*-
"""JarvisDevAgent — Agente autônomo com Thought Stream."""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)

_JOBS_FILE = Path("data/dev_agent_jobs.jsonl")
_MAX_ITERATIONS = int(os.getenv("DEV_AGENT_MAX_ITERATIONS", "12"))


class JarvisDevAgent(NexusComponent):
    """Agente autônomo com Thought Stream blindado contra falhas de I/O e LLM."""
    
    def __init__(self) -> None:
        super().__init__()
        self.max_iterations: int = _MAX_ITERATIONS
        self._thought_log = None
        self._shell = None
        self._editor = None
        self._llm = None
    
    def _get_thought_log(self):
        if self._thought_log is None:
            self._thought_log = nexus.resolve("thought_log_service")
        return self._thought_log
    
    def _get_shell(self):
        if self._shell is None:
            self._shell = nexus.resolve("persistent_shell_adapter")
        return self._shell
    
    def _get_editor(self):
        if self._editor is None:
            self._editor = nexus.resolve("surgical_edit_service")
        return self._editor
    
    def _get_llm(self):
        if self._llm is None:
            self._llm = nexus.resolve("llm_router")
        return self._llm

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa tarefa com Thought Stream."""
        ctx = context or {}
        task_id = ctx.get("task_id", f"task_{uuid.uuid4().hex[:12]}")
        description = ctx.get("description", "")
        
        thought_log = self._get_thought_log()
        if thought_log:
            thought_log.stream_planning(f"🚀 Missão: {description[:100]}")
            thought_log.execute({
                "action": "create_thought",
                "mission_id": task_id,
                "session_id": f"session_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "thought_process": f"Iniciando missão: {description}",
                "problem_description": description,
                "success": True,
            })
        
        logger.info(f"🤖 [JarvisDevAgent] task_id={task_id}")
        
        try:
            result = self._run_loop(task_id, description, ctx)
            
            if thought_log:
                if result.get("success"):
                    thought_log.stream_success(
                        f"✅ Completado em {result.get('iterations', 0)} iterações"
                    )
                else:
                    thought_log.stream_error(f"❌ Falha: {result.get('error', 'Erro desconhecido')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Erro fatal no JarvisDevAgent: {e}", exc_info=True)
            if thought_log:
                thought_log.stream_error(f"💥 Erro fatal: {str(e)}")
            return {"success": False, "task_id": task_id, "error": str(e)}
    
    def _run_loop(self, task_id: str, description: str, ctx: Dict) -> Dict[str, Any]:
        """Loop iterativo com Thought Stream e tolerância a falhas."""
        shell = self._get_shell()
        editor = self._get_editor()
        llm = self._get_llm()
        thought_log = self._get_thought_log()
        
        if thought_log:
            thought_log.stream_planning("🔍 Mapeando estrutura...")
        
        # Prevenção contra retornos nulos do shell
        structure_res = shell.execute({"command": "find . -maxdepth 2 -name '*.py' | head -20"}) or {}
        structure_output = str(structure_res.get('output', ''))
        
        if thought_log and structure_output:
            thought_log.stream_observation(f"📁 {structure_output[:200]}")
        
        iteration = 0
        history: List[Dict[str, Any]] = []
        
        while iteration < self.max_iterations:
            iteration += 1
            
            if thought_log:
                thought_log.stream_info(f"🔄 Iteração {iteration}/{self.max_iterations}")
                thought_log.stream_planning("🧠 LLM decidindo...")
            
            prompt = self._build_prompt(description, history[-5:], structure_output)
            
            # Execução segura do LLM
            decision_res = llm.execute({"prompt": prompt, "require_json": True}) or {}
            raw_result = str(decision_res.get('result', ''))
            
            action_data = self._extract_json(raw_result)
            
            if not action_data:
                if thought_log:
                    thought_log.stream_error("❌ LLM não retornou um JSON de ação válido")
                return {
                    "success": False, 
                    "error": "LLM retornou formato inválido", 
                    "iteration": iteration,
                    "raw_response": raw_result[:500]
                }
            
            action_type = action_data.get("action", "FINISH")
            params = action_data.get("params") or {} # Garante que params seja um dict, mesmo se o LLM enviar null
            
            if thought_log:
                thought_log.stream_action(f"⚡ {action_type}")
            
            # Executa a ação isolando possíveis quebras
            observation = self._execute_action(action_type, params, shell, editor)
            
            if thought_log:
                obs_preview = observation[:200] + "..." if len(observation) > 200 else observation
                thought_log.stream_observation(f"👁️ {obs_preview}")
            
            history.append({
                "iteration": iteration, 
                "action": action_type, 
                "observation": observation
            })
            
            if action_type == "FINISH":
                if thought_log:
                    thought_log.stream_success("✅ Finalizado")
                return {
                    "success": True, 
                    "task_id": task_id, 
                    "iterations": iteration, 
                    "history": history
                }
        
        if thought_log:
            thought_log.stream_error(f"⚠️ Limite de iterações atingido ({self.max_iterations})")
        
        return {
            "success": False, 
            "task_id": task_id, 
            "error": f"Limite de {self.max_iterations} iterações", 
            "iterations": iteration
        }
    
    def _build_prompt(self, description: str, history: List[Dict], structure: str) -> str:
        """Constrói prompt robusto para o LLM."""
        formatted_history = []
        for h in history:
            act = h.get('action', 'UNKNOWN')
            obs = str(h.get('observation', ''))[:150].replace('\n', ' ')
            formatted_history.append(f"Iter {h.get('iteration', '?')}: {act} → {obs}")
            
        history_text = "\n".join(formatted_history) or "(Nenhuma)"
        
        return (
            f"Tarefa: {description}\n"
            f"Estrutura:\n{structure[:1000]}\n"
            f"Histórico Recente:\n{history_text}\n\n"
            f"Ações válidas: RUN_SHELL, EDIT_FILE, READ_FILE, INSTALL_DEPS, FINISH\n"
            f"Obrigatório retornar JSON EXATAMENTE neste formato: {{\"action\": \"...\", \"params\": {{}}}}"
        )
    
    def _execute_action(self, action_type: str, params: Dict, shell, editor) -> str:
        """Executa ação baseada no tipo, blindada contra erros de I/O e tipagem."""
        try:
            if action_type == "RUN_SHELL":
                cmd = params.get("cmd", "")
                res = shell.execute({"command": cmd}) or {}
                return str(res.get("output", "Sem saída no terminal."))[:1500]
                
            elif action_type == "EDIT_FILE":
                res = editor.execute({
                    "file_path": params.get("path"), 
                    "search_block": params.get("search"), 
                    "replace_block": params.get("replace")
                }) or {}
                # Captura de resposta adaptativa caso o editor retorne chaves diferentes
                return str(res.get("action", res.get("status", res.get("message", "Edição solicitada."))))
                
            elif action_type == "READ_FILE":
                res = editor.execute({"file_path": params.get("path")}) or {}
                return str(res.get("content", "Arquivo vazio ou não encontrado."))[:1500]
                
            elif action_type == "INSTALL_DEPS":
                pkgs = params.get('packages', [])
                # Tratamento caso o LLM envie string ou tipo inesperado
                if isinstance(pkgs, str):
                    pkgs = [pkgs]
                elif not isinstance(pkgs, list):
                    pkgs = []
                    
                pkgs_str = " ".join(str(p) for p in pkgs)
                if not pkgs_str:
                    return "Nenhum pacote especificado para instalação."
                    
                res = shell.execute({"command": f"pip install {pkgs_str}"}) or {}
                return str(res.get("output", "Instalação concluída."))[:1500]
                
            elif action_type == "FINISH":
                return str(params.get("summary", "Fluxo finalizado com sucesso."))
                
            return f"Ação desconhecida ou não suportada: {action_type}"
            
        except Exception as e:
            logger.error(f"Falha ao executar ação {action_type}: {e}")
            return f"Erro interno ao executar a ação {action_type}: {str(e)}"
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extrai JSON de resposta."""
        match = re.search(r'```(?:json)?\s*({.*?})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        try:
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except:
            pass
        return None
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True