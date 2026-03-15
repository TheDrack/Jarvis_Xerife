# -*- coding: utf-8 -*-
"""Actions — Executa ações do agente."""
import importlib
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict
from app.core.nexus import nexus
from app.domain.models.agent import AgentAction, AgentObservation, ActionType

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executa ações decididas pelo agente."""
    
    def __init__(self):
        self._shell_adapter = None
        self._code_discovery = None
    
    def _get_shell_adapter(self):
        if self._shell_adapter is None:
            self._shell_adapter = nexus.resolve("persistent_shell_adapter")
        return self._shell_adapter
    
    def _get_code_discovery(self):
        if self._code_discovery is None:
            from .code_discovery import CodeDiscovery
            self._code_discovery = CodeDiscovery()
        return self._code_discovery
    
    def execute(self, action: AgentAction) -> AgentObservation:
        """Executa ação e retorna observação."""
        start_time = time.time()
        
        try:
            handler = self._get_handler(action.action_type)
            output = handler(action.parameters)
            
            return AgentObservation(
                action=action,
                output=output,
                success=True,
                execution_time_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return AgentObservation(
                action=action,
                output="",                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )
    
    def _get_handler(self, action_type):
        handlers = {
            ActionType.RUN_FUNCTION: self._run_function,
            ActionType.RUN_SHELL: self._run_shell,
            ActionType.RUN_TESTS: self._run_tests,
            ActionType.READ_FILE: self._read_file,
            ActionType.EDIT_FILE: self._edit_file,
            ActionType.BROWSE: self._browse,
            ActionType.SEARCH_CODE: self._search_code,
            ActionType.CREATE_PIPELINE: self._create_pipeline,
            ActionType.RUN_PIPELINE: self._run_pipeline,
            ActionType.FINISH: self._finish,
        }
        return handlers.get(action_type, self._unknown)
    
    def _run_function(self, params: Dict[str, Any]) -> str:
        function_name = params.get("function_name", "")
        if not function_name:
            return "ERRO: function_name não fornecido"
        
        try:
            component = nexus.resolve(function_name)
            if component and not getattr(component, "__is_cloud_mock__", False):
                if hasattr(component, "execute"):
                    result = component.execute(params.get("kwargs", {}))
                    return f"✅ {function_name} executada\n{str(result)[:500]}"
            return f"❌ Função não encontrada: {function_name}"
        except Exception as e:
            return f"❌ Erro: {e}"
    
    def _run_shell(self, params: Dict[str, Any]) -> str:
        command = params.get("command", "")
        if not command:
            return "ERRO: Comando vazio"
        
        adapter = self._get_shell_adapter()
        if adapter and not getattr(adapter, "__is_cloud_mock__", False):
            result = adapter.execute({"action": "run_command", "command": command})
            return result.get("output", result.get("error", "Sem output"))
        
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout + result.stderr
    
    def _run_tests(self, params: Dict[str, Any]) -> str:
        test_path = params.get("test_path", "tests/")        try:
            result = subprocess.run(
                ["pytest", test_path, "-v", "--tb=short"],
                capture_output=True, text=True, timeout=120,
            )
            return result.stdout[:3000] + result.stderr[:1000]
        except Exception as e:
            return f"ERRO: {e}"
    
    def _read_file(self, params: Dict[str, Any]) -> str:
        path = params.get("path", "")
        if not path:
            return "ERRO: Path vazio"
        try:
            content = Path(path).read_text()[:5000]
            return f"=== {path} ===\n{content}"
        except Exception as e:
            return f"ERRO: {e}"
    
    def _edit_file(self, params: Dict[str, Any]) -> str:
        path, content = params.get("path", ""), params.get("content", "")
        if not path or not content:
            return "ERRO: Path ou content vazio"
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            return f"✅ Arquivo: {path} ({len(content)} bytes)"
        except Exception as e:
            return f"ERRO: {e}"
    
    def _browse(self, params: Dict[str, Any]) -> str:
        path = params.get("path", ".")
        try:
            items = [f"{'📁' if p.is_dir() else '📄'} {p.name}" for p in Path(path).iterdir()]
            return f"=== {path} ===\n" + "\n".join(sorted(items))
        except Exception as e:
            return f"ERRO: {e}"
    
    def _search_code(self, params: Dict[str, Any]) -> str:
        pattern, path = params.get("pattern", ""), params.get("path", ".")
        if not pattern:
            return "ERRO: Pattern vazio"
        try:
            result = subprocess.run(
                ["grep", "-r", "-n", pattern, path],
                capture_output=True, text=True, timeout=30,
            )
            return result.stdout[:3000] or "Nenhuma correspondência"
        except Exception as e:            return f"ERRO: {e}"
    
    def _create_pipeline(self, params: Dict[str, Any]) -> str:
        from .pipeline_builder import PipelineBuilder
        builder = PipelineBuilder()
        name = params.get("name", "auto_pipeline")
        steps = params.get("steps", [])
        
        path = builder.create_pipeline(name=name, steps=steps)
        return f"✅ Pipeline criado: {path}"
    
    def _run_pipeline(self, params: Dict[str, Any]) -> str:
        from .pipeline_builder import PipelineBuilder
        builder = PipelineBuilder()
        name = params.get("pipeline_name", "")
        
        result = builder.run_pipeline(name)
        return f"✅ Pipeline executado: {name}" if result.get("success") else f"❌ Erro: {result.get('error')}"
    
    def _finish(self, params: Dict[str, Any]) -> str:
        return params.get("final_summary", "Tarefa finalizada")
    
    def _unknown(self, params: Dict[str, Any]) -> str:
        return "ERRO: Ação desconhecida"