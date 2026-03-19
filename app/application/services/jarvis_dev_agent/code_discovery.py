# -*- coding: utf-8 -*-
"""CodeDiscovery — Descobre funções/classes no repositório."""
import ast
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.nexus import nexus

logger = logging.getLogger(__name__)


class CodeDiscovery:
    """Descobre funções, classes e serviços existentes no repo."""
    
    def __init__(self):
        self._context_service = None
        self._cache: Optional[Dict[str, Any]] = None
    
    def _get_context_service(self):
        """Lazy loading do ConsolidatedContextService."""
        if self._context_service is None:
            self._context_service = nexus.resolve("consolidated_context_service")
        return self._context_service
    
    def discover(self, refresh: bool = False) -> Dict[str, Any]:
        """Descobre código existente no repositório."""
        if self._cache and not refresh:
            return self._cache
        
        discovered = {"functions": [], "classes": [], "services": []}
        
        context_data = self._discover_from_context()
        if context_data:
            # Garante que as chaves existam antes de atualizar
            for key in ["functions", "classes"]:
                if key in context_data:
                    discovered[key].extend(context_data[key])
        
        ast_data = self._discover_from_ast()
        for key in ["functions", "classes"]:
            if key in ast_data:
                discovered[key].extend(ast_data[key])
        
        self._cache = discovered
        logger.info(f"🔍 [CodeDiscovery] {len(discovered['functions'])} funções encontradas")
        return discovered
    
    def _discover_from_context(self) -> Optional[Dict[str, Any]]:
        """Extrai informações do consolidated context."""
        try:
            service = self._get_context_service()
            if service and not getattr(service, "__is_cloud_mock__", False):
                result = service.execute({"action": "get_info"})
                context = result.get("context", "")
                
                functions = self._extract_functions_from_context(context)
                classes = self._extract_classes_from_context(context)
                
                return {"functions": functions, "classes": classes}
        except Exception as e:
            logger.debug(f"[CodeDiscovery] Erro ao ler contexto: {e}")
        return None
    
    def _discover_from_ast(self) -> Dict[str, Any]:
        """Analisa arquivos Python com AST."""
        functions = []
        classes = []
        
        target_dirs = [
            Path("app/application/services"),
            Path("app/adapters/infrastructure"),
            Path("app/domain/services"),
        ]
        
        for target_dir in target_dirs:
            if not target_dir.exists():
                continue
            
            for py_file in target_dir.rglob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                
                try:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(content)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if not node.name.startswith("_"):
                                functions.append({
                                    "name": node.name,
                                    "file": str(py_file),
                                    "line": node.lineno,
                                })
                        elif isinstance(node, ast.ClassDef):
                            if not node.name.startswith("_"):
                                classes.append({
                                    "name": node.name,
                                    "file": str(py_file),
                                    "line": node.lineno,
                                })
                except Exception:
                    continue
        
        return {"functions": functions, "classes": classes}

    def _extract_functions_from_context(self, context: str) -> List[Dict[str, Any]]:
        """Extrai menções de funções do consolidated context."""
        functions = []
        if not context:
            return functions
            
        pattern = r"def\s+(\w+)\s*\("
        matches = re.findall(pattern, context)
        for match in matches[:50]:
            if not match.startswith("_"):
                functions.append({"name": match, "source": "context"})
        return functions
    
    def _extract_classes_from_context(self, context: str) -> List[Dict[str, Any]]:
        """Extrai menções de classes do consolidated context."""
        classes = []
        if not context:
            return classes
            
        pattern = r"class\s+(\w+)\s*\("
        matches = re.findall(pattern, context)
        for match in matches[:50]:
            if not match.startswith("_"):
                classes.append({"name": match, "source": "context"})
        return classes
    
    def find_function(self, name_or_pattern: str) -> List[Dict[str, Any]]:
        """Busca função por nome ou padrão."""
        discovered = self.discover()
        matches = []
        for func in discovered.get("functions", []):
            if name_or_pattern.lower() in func["name"].lower():
                matches.append(func)
        return matches
    
    def find_class(self, name_or_pattern: str) -> List[Dict[str, Any]]:
        """Busca classe por nome ou padrão."""
        discovered = self.discover()
        matches = []
        for cls in discovered.get("classes", []):
            if name_or_pattern.lower() in cls["name"].lower():
                matches.append(cls)
        return matches
