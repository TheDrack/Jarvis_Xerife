# -*- coding: utf-8 -*-
"""CuriosityEngine — Motor de curiosidade e exploração proativa."""
import logging
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.nexus import NexusComponent, nexus

logger = logging.getLogger(__name__)


class CuriosityEngine(NexusComponent):
    """
    Motor de curiosidade que identifica gaps de conhecimento e oportunidades.
    
    Funcionalidades:
    - Identifica padrões não explorados no código
    - Sugere melhorias baseadas em análise estática
    - Integra com ProceduralMemory para aprendizado
    - Gera tasks para JarvisDevAgent
    """
    
    def __init__(self):
        super().__init__()
        self._memory = None
        self._llm = None
    
    def _get_memory(self):
        """Lazy loading do ProceduralMemory."""
        if self._memory is None:
            self._memory = nexus.resolve("procedural_memory")
        return self._memory
    
    def _get_llm(self):
        """Lazy loading do LLMRouter."""
        if self._llm is None:
            self._llm = nexus.resolve("llm_router")
        return self._llm
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """NexusComponent contract."""
        return True
    
    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa análise de curiosidade e gera insights.
        
        Args:
            context: Contexto de execução            
        Returns:
            Dict com insights e oportunidades
        """
        ctx = context or {}
        action = ctx.get("action", "analyze")
        
        if action == "analyze":
            return self._analyze_gaps(ctx)
        elif action == "explore":
            return self._explore_opportunities(ctx)
        elif action == "suggest":
            return self._suggest_improvements(ctx)
        
        return {"success": False, "error": f"Ação desconhecida: {action}"}
    
    def _analyze_gaps(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa gaps de conhecimento/capabilidade."""
        logger.info("[CuriosityEngine] Analisando gaps...")
        
        gaps = []
        
        try:
            registry_path = Path("data/nexus_registry.json")
            if registry_path.exists():
                registry = json.loads(registry_path.read_text())
                components = registry.get("components", {})
                
                for comp_id, comp_info in components.items():
                    if "adapter" in comp_id.lower():
                        memory = self._get_memory()
                        if memory:
                            usage = memory.execute({
                                "action": "find_similar",
                                "query": comp_id,
                                "top_k": 1
                            })
                            if not usage.get("results"):
                                gaps.append({
                                    "type": "unused_adapter",
                                    "component": comp_id,
                                    "suggestion": f"Considerar remover ou usar {comp_id}"
                                })
        except Exception as e:
            logger.debug(f"[CuriosityEngine] Erro ao analisar gaps: {e}")
            
        return {
            "success": True,
            "gaps": gaps,
            "total_gaps": len(gaps)
        }
    
    def _explore_opportunities(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Explora oportunidades de melhoria."""
        logger.info("[CuriosityEngine] Explorando oportunidades...")
        
        opportunities = []
        
        try:
            app_path = Path("app")
            if app_path.exists():
                for py_file in app_path.rglob("*.py"):
                    if py_file.name.startswith("_"):
                        continue
                    
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    lines = content.split("\n")
                    
                    if len(lines) > 250:
                        opportunities.append({
                            "type": "long_file",
                            "file": str(py_file),
                            "lines": len(lines),
                            "suggestion": "Dividir em módulos menores"
                        })
                    
                    import_count = content.count("import ") + content.count("from ")
                    if import_count > 25:
                        opportunities.append({
                            "type": "many_imports",
                            "file": str(py_file),
                            "imports": import_count,
                            "suggestion": "Revisar imports não utilizados ou excessivos"
                        })
        except Exception as e:
            logger.debug(f"[CuriosityEngine] Erro ao explorar: {e}")
        
        return {
            "success": True,
            "opportunities": opportunities,
            "total_opportunities": len(opportunities)
        }
    
    def _suggest_improvements(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Sugere melhorias baseadas em análise."""
        logger.info("[CuriosityEngine] Gerando sugestões...")
        
        suggestions = []
        
        llm = self._get_llm()
        if llm and not getattr(llm, "__is_cloud_mock__", False):
            try:
                prompt = """
Analise a estrutura do projeto JARVIS e sugira 3 melhorias de arquitetura.
Considere:
1. Modularização de arquivos grandes
2. Otimização de imports
3. Padronização de código

Retorne JSON: {"suggestions": [{"area": "...", "improvement": "...", "priority": "high/medium/low"}]}
"""
                result = llm.execute({
                    "task_type": "code_generation",
                    "prompt": prompt,
                    "require_json": True,
                    "temperature": 0.3
                })
                
                response = result.get("result", "")
                match = re.search(r'\{.*\}', response, re.DOTALL)
                if match:
                    suggestions_data = json.loads(match.group())
                    suggestions = suggestions_data.get("suggestions", [])
            except Exception as e:
                logger.debug(f"[CuriosityEngine] Erro ao gerar sugestões: {e}")
        
        return {
            "success": True,
            "suggestions": suggestions,
            "total_suggestions": len(suggestions)
        }
