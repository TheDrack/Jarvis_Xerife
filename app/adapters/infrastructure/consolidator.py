# -*- coding: utf-8 -*-
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class RepositoryConsolidator:
    """
    Componente responsável por consolidar o código fonte em snapshots operacionais.
    """

    def __init__(self):
        # A única alteração em todo o arquivo é a vírgula após "markdown"
        self.supported_extensions = {
            ".py": "python",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
            ".md": "markdown"
        }

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point via Nexus DI."""
        action = context.get("action", "consolidate")
        
        if action == "consolidate":
            root_path = context.get("root_path", os.getcwd())
            return self.run_consolidation(root_path)
        
        return {"success": False, "not_implemented": True}

    def run_consolidation(self, root_path: str) -> Dict[str, Any]:
        """Varre o repositório e gera um snapshot do código."""
        logger.info(f"[Consolidator] Iniciando consolidação em: {root_path}")
        
        consolidated_data = []
        
        try:
            for root, dirs, files in os.walk(root_path):
                if any(d in root for d in [".git", "__pycache__", "venv", ".venv"]):
                    continue
                
                for file in files:
                    ext = os.path.splitext(file)[1]
                    if ext in self.supported_extensions:
                        file_path = os.path.join(root, file)
                        
                        try:
                            f = open(file_path, 'r', encoding='utf-8')
                            content = f.read()
                            f.close()
                            
                            consolidated_data.append({
                                "file": os.path.relpath(file_path, root_path),
                                "type": self.supported_extensions[ext],
                                "content": content
                            })
                        except Exception as e:
                            logger.warning(f"[Consolidator] Erro ao ler {file}: {e}")

            return {
                "success": True,
                "snapshot_size": len(consolidated_data),
                "data": consolidated_data
            }

        except Exception as e:
            logger.error(f"[Consolidator] Falha crítica: {e}")
            return {"success": False, "error": str(e)}
