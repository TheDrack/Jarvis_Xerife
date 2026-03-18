# -*- coding: utf-8 -*-
import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class CodeDiscoveryService:
    """
    Serviço de exploração de código.
    Permite ao JARVIS mapear o projeto e ler conteúdos de ficheiros de forma segura.
    """

    def __init__(self, root_path: str):
        self.root_path = root_path
        self.ignore_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules", ".pytest_cache"}

    def scan_project_structure(self) -> Dict[str, Any]:
        """Mapeia a árvore de diretórios do projeto."""
        structure = {}
        
        for root, dirs, files in os.walk(self.root_path):
            # CORREÇÃO: Filtro de diretórios a ignorar para evitar recursão infinita ou lenta
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            
            relative_path = os.path.relpath(root, self.root_path)
            if relative_path == ".":
                relative_path = "root"
            
            # CORREÇÃO: Sintaxe e limpeza da lista de ficheiros
            structure[relative_path] = [f for f in files if not f.startswith(".")]
            
        return structure

    async def find_relevant_context(self, query: str) -> List[Dict[str, str]]:
        """
        Procura ficheiros que possam estar relacionados com o problema descrito.
        Nota: Esta é uma implementação base que pode ser expandida com busca vetorial.
        """
        results = []
        all_files = []
        
        for root, _, files in os.walk(self.root_path):
            if any(id_dir in root for id_dir in self.ignore_dirs):
                continue
            for f in files:
                if f.endswith((".py", ".yml", ".yaml", ".json", ".md")):
                    all_files.append(os.path.join(root, f))

        # Busca simples por palavra-chave no nome do ficheiro (Surgical Discovery)
        keywords = query.lower().split()
        for path in all_files:
            if any(kw in path.lower() for kw in keywords):
                content = self.get_file_content(path)
                if content:
                    results.append({
                        "path": os.path.relpath(path, self.root_path),
                        "content": content
                    })
        
        return results[:5]  # Limita a 5 ficheiros para não estourar o contexto do LLM

    def get_file_content(self, file_path: str) -> Optional[str]:
        """Lê o conteúdo de um ficheiro de forma segura."""
        full_path = os.path.join(self.root_path, file_path) if not os.path.isabs(file_path) else file_path
        
        # CORREÇÃO: Validação de existência e leitura com erro tratado
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            return None
            
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except (UnicodeDecodeError, PermissionError) as e:
            logger.warning(f"[Discovery] Não foi possível ler {file_path}: {e}")
            return None
