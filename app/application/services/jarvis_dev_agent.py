# -*- coding: utf-8 -*-
"""JarvisDevAgent — Agente autônomo com loop iterativo (Devin-style).

Features:
- Pre-flight check (mapeia estrutura do projeto)
- Loop iterativo com working memory
- Surgical edit para precisão
- Persistent shell para execução
- Auto-instalação de dependências
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent, nexus
from app.domain.models.agent import AgentAction, AgentTask, TaskSource, TaskPriority, ActionType

logger = logging.getLogger(__name__)

_JOBS_FILE = Path("data/dev_agent_jobs.jsonl")
_MAX_ITERATIONS = int(os.getenv("DEV_AGENT_MAX_ITERATIONS", "12"))
_MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "8000"))


class JarvisDevAgent(NexusComponent):
    """Agente autônomo de desenvolvimento com loop iterativo."""
    
    def __init__(self) -> None:
        super().__init__()
        self.max_iterations: int = _MAX_ITERATIONS
        self._shell = None
        self._editor = None
        self._memory = None
        self._llm = None
    
    def _get_shell(self):
        """Lazy loading do PersistentShellAdapter."""
        if self._shell is None:
            self._shell = nexus.resolve("persistent_shell_adapter")
        return self._shell
    
    def _get_editor(self):
        """Lazy loading do SurgicalEditService."""
        if self._editor is None:
            self._editor = nexus.resolve("surgical_edit_service")        return self._editor
    
    def _get_memory(self):
        """Lazy loading do WorkingMemory."""
        if self._memory is None:
            self._memory = nexus.resolve("working_memory")
        return self._memory
    
    def _get_llm(self):
        """Lazy loading do LLMRouter."""
        if self._llm is None:
            self._llm = nexus.resolve("llm_router")
        return self._llm
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executa tarefa autônoma com loop iterativo."""
        ctx = context or {}
        task = self._create_task(ctx)
        
        logger.info(f"🤖 [JarvisDevAgent] task_id={task.task_id} source={task.source.value}")
        
        try:
            result = self._execute_cycle(task, ctx)
            self._record_result(task, result)
            return result
        except Exception as e:
            logger.error(f"❌ [JarvisDevAgent] Erro: {e}", exc_info=True)
            return {"success": False, "task_id": task.task_id, "error": str(e)}
    
    def _create_task(self, ctx: Dict[str, Any]) -> AgentTask:
        """Cria tarefa do contexto."""
        return AgentTask(
            task_id=ctx.get("task_id", f"task_{uuid.uuid4().hex[:12]}"),
            source=TaskSource(ctx.get("source", "user_request")),
            priority=TaskPriority(ctx.get("priority", "medium")),
            description=ctx.get("description", ""),
            context=ctx.get("context", {}),
            constraints=ctx.get("constraints", []),
            success_criteria=ctx.get("success_criteria", "Tarefa completada"),
        )
    
    def _execute_cycle(self, task: AgentTask, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Loop iterativo com pre-flight check."""
        shell = self._get_shell()
        editor = self._get_editor()
        memory = self._get_memory()
        llm = self._get_llm()
        
        if not all([shell, editor, memory, llm]):
            return {"success": False, "error": "Componentes necessários indisponíveis"}        
        # === PRE-FLIGHT CHECK ===
        logger.info("🔍 [JarvisDevAgent] Pre-flight check: mapeando estrutura...")
        structure = shell.execute({"command": "find . -maxdepth 2 -type f -name '*.py' | head -20"})
        logger.info(f"📁 Estrutura mapeada: {structure.get('output', '')[:200]}")
        
        # === LOOP ITERATIVO ===
        iteration = 0
        history = []
        
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"🔄 [JarvisDevAgent] Iteração {iteration}/{self.max_iterations}")
            
            # 1. Prepara contexto (com truncagem)
            recent_history = history[-5:] if len(history) > 5 else history
            prompt = self._build_prompt(task, recent_history, structure.get('output', ''))
            
            # 2. Decisão do LLM
            decision = llm.execute({
                "task_type": "code_generation",
                "prompt": prompt,
                "require_json": True,
                "temperature": 0.1
            })
            
            action_data = self._extract_json(decision.get('result', ''))
            if not action_data:
                return {"success": False, "error": "LLM não retornou ação válida", "iteration": iteration}
            
            action_type = action_data.get("action", "FINISH")
            params = action_data.get("params", {})
            reasoning = action_data.get("reasoning", "")
            
            logger.info(f"🎯 Ação: {action_type} — {reasoning[:100]}")
            
            # 3. Executa ação
            observation = self._execute_action(action_type, params, shell, editor)
            
            # 4. Armazena na memória
            history.append({
                "iteration": iteration,
                "action": action_type,
                "params": params,
                "reasoning": reasoning,
                "observation": observation
            })
            
            # 5. Verifica se finalizou
            if action_type == "FINISH":                logger.info(f"✅ [JarvisDevAgent] Finalizado na iteração {iteration}")
                return {
                    "success": True,
                    "task_id": task.task_id,
                    "iterations": iteration,
                    "history": history,
                    "final_result": observation
                }
            
            # 6. Verifica erro repetitivo
            if self._is_repetitive_error(observation, history):
                logger.warning("⚠️ [JarvisDevAgent] Erro repetitivo detectado")
                # Continua mas com aviso no próximo prompt
        
        # Limite de iterações
        return {
            "success": False,
            "task_id": task.task_id,
            "error": f"Limite de {self.max_iterations} iterações atingido",
            "iterations": iteration,
            "history": history
        }
    
    def _build_prompt(self, task: AgentTask, history: List[Dict], structure: str) -> str:
        """Constrói prompt com contexto truncado."""
        history_text = "\n".join([
            f"Iteração {h['iteration']}: {h['action']} → {h['observation'][:200]}"
            for h in history[-5:]
        ]) or "(Nenhuma ação anterior)"
        
        constraints = "\n".join(task.constraints) if task.constraints else "Nenhuma"
        
        return f"""
Você é o JarvisDevAgent — agente autônomo de desenvolvimento.

=== TAREFA ===
Descrição: {task.description}
Critérios: {task.success_criteria}
Restrições: {constraints}

=== ESTRUTURA DO PROJETO ===
{structure[:2000]}

=== HISTÓRICO DE AÇÕES ===
{history_text}

=== AÇÕES DISPONÍVEIS ===
- RUN_SHELL: {{ "action": "RUN_SHELL", "params": {{"cmd": "pytest tests/"}} }}
- EDIT_FILE: {{ "action": "EDIT_FILE", "params": {{"path": "app/file.py", "search": "...", "replace": "..."}} }}
- READ_FILE: {{ "action": "READ_FILE", "params": {{"path": "app/file.py"}} }}- INSTALL_DEPS: {{ "action": "INSTALL_DEPS", "params": {{"packages": ["requests", "numpy"]}} }}
- FINISH: {{ "action": "FINISH", "params": {{"summary": "Tarefa completada"}} }}

=== INSTRUÇÕES ===
1. Se precisar instalar pacotes, use INSTALL_DEPS (ambiente seguro)
2. Para editar código, use EDIT_FILE com search/replace exato
3. Se encontrar "Command not found", instale automaticamente
4. Retorne APENAS JSON da ação

Retorne APENAS o JSON:
"""
    
    def _execute_action(self, action_type: str, params: Dict, shell, editor) -> str:
        """Executa ação e retorna observação."""
        if action_type == "RUN_SHELL":
            result = shell.execute({"command": params.get("cmd", "")})
            return result.get("output", result.get("error", ""))
        
        elif action_type == "EDIT_FILE":
            result = editor.execute({
                "action": "apply_edit",
                "file_path": params.get("path", ""),
                "search_block": params.get("search", ""),
                "replace_block": params.get("replace", "")
            })
            return result.get("action", result.get("error", ""))
        
        elif action_type == "READ_FILE":
            result = editor.execute({
                "action": "read_file",
                "file_path": params.get("path", "")
            })
            return result.get("content", result.get("error", ""))[:1000]
        
        elif action_type == "INSTALL_DEPS":
            packages = params.get("packages", [])
            result = shell.execute({"command": f"pip install {' '.join(packages)}"})
            return result.get("output", result.get("error", ""))
        
        elif action_type == "FINISH":
            return params.get("summary", "Tarefa finalizada")
        
        return f"Ação desconhecida: {action_type}"
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extrai JSON de resposta do LLM."""
        import re
        match = re.search(r'```(?:json)?\s*({.*?})\s*```', text, re.DOTALL)
        if match:
            try:                return json.loads(match.group(1))
            except:
                pass
        try:
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except:
            pass
        return None
    
    def _is_repetitive_error(self, observation: str, history: List[Dict]) -> bool:
        """Verifica se erro já ocorreu nas últimas iterações."""
        if not observation or "error" not in observation.lower():
            return False
        
        recent_errors = [
            h.get("observation", "")
            for h in history[-3:]
            if "error" in h.get("observation", "").lower()
        ]
        
        return any(observation[:100] in err for err in recent_errors)
    
    def _record_result(self, task: AgentTask, result: Dict[str, Any]) -> None:
        """Registra resultado no jobs log."""
        try:
            _JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "task_id": task.task_id,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "success": result.get("success", False),
                "source": task.source.value,
                "iterations": result.get("iterations", 0),
            }
            with open(_JOBS_FILE, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"[JarvisDevAgent] Erro ao registrar: {e}")
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True