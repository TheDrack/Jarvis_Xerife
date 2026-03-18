# -*- coding: utf-8 -*-
import os
import logging
from typing import Dict, Any, List
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

class RepositoryConsolidator(NexusComponent):
    """
    Componente responsável por consolidar o código fonte em snapshots operacionais.
    Essencial para fornecer contexto denso ao MetabolismCore.
    """

    def __init__(self):
        super().__init__()
        # CORREÇÃO: Sintaxe corrigida na linha 37 (mapeamento de extensões)
        self.supported_extensions = {
            ".py": "python",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
            ".md": "markdown"
        }
        self.max_file_size = 500 * 1024  # Limite de 500KB por ficheiro

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point via Nexus DI."""
        action = context.get("action", "consolidate")
        
        if action == "consolidate":
            root_path = context.get("root_path", os.getcwd())
            return self.run_consolidation(root_path)
        
        return {"success": False, "error": f"Ação '{action}' não suportada."}

    def run_consolidation(self, root_path: str) -> Dict[str, Any]:
        """Varre o repositório e gera um snapshot do código."""
        logger.info(f"[Consolidator] Iniciando consolidação em: {root_path}")
        
        consolidated_data = []
        
        try:
            for root, dirs, files in os.walk(root_path):
                # Ignora diretórios ocultos e de build
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'venv']
                
                for file in files:
                    ext = os.path.splitext(file)[1]
                    if ext in self.supported_extensions:
                        file_path = os.path.join(root, file)
                        
                        # CORREÇÃO: Verificação de tamanho e gestão de fecho de ficheiro
                        if os.path.getsize(file_path) > self.max_file_size:
                            continue
                            
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
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
