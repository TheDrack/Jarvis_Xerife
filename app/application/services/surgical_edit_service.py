# -*- coding: utf-8 -*-
"""SurgicalEditService — Edição cirúrgica de arquivos (Search/Replace).

Evita que o LLM reescreva arquivos inteiros, aplicando apenas
mudanças pontuais com validação exata do bloco de busca.
"""
import os
import logging
from typing import Dict, Any, Optional
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)


class SurgicalEditService(NexusComponent):
    """Serviço de edição cirúrgica de arquivos."""
    
    def __init__(self):
        super().__init__()
        self._max_file_size = int(os.getenv("MAX_FILE_SIZE", "100000"))  # 100KB
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """NexusComponent entry-point."""
        config = context.get("current_config", {}) or context.get("config", {})
        
        action = config.get("action") or context.get("action", "apply_edit")
        file_path = config.get("file_path") or context.get("file_path", "")
        search_block = config.get("search_block") or context.get("search_block", "")
        replace_block = config.get("replace_block") or context.get("replace_block", "")
        
        if action == "apply_edit":
            return self.apply_edit(file_path, search_block, replace_block)
        elif action == "read_file":
            return self.read_file(file_path)
        elif action == "write_file":
            content = config.get("content") or context.get("content", "")
            return self.write_file(file_path, content)
        else:
            return {"success": False, "error": f"Ação desconhecida: {action}"}
    
    def apply_edit(self, file_path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
        """
        Aplica alteração cirúrgica em arquivo.
        
        Args:
            file_path: Caminho do arquivo
            search_block: Bloco exato a buscar
            replace_block: Bloco para substituição
        
        Returns:            Dict com status da operação
        """
        if not file_path:
            return {"success": False, "error": "file_path não fornecido"}
        
        if not os.path.exists(file_path):
            return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}
        
        # Verifica tamanho
        if os.path.getsize(file_path) > self._max_file_size:
            return {"success": False, "error": f"Arquivo muito grande (> {self._max_file_size} bytes)"}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not search_block:
                return {"success": False, "error": "search_block vazio"}
            
            if search_block not in content:
                # Tenta busca fuzzy (linhas similares)
                return {
                    "success": False,
                    "error": "search_block não encontrado exatamente",
                    "hint": "Verifique indentação e caracteres especiais"
                }
            
            new_content = content.replace(search_block, replace_block, 1)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            logger.info(f"[SurgicalEdit] Arquivo editado: {file_path}")
            return {
                "success": True,
                "file": file_path,
                "action": "edit",
                "bytes_changed": abs(len(new_content) - len(content))
            }
            
        except Exception as e:
            logger.error(f"[SurgicalEdit] Erro: {e}")
            return {"success": False, "error": str(e)}
    
    def read_file(self, file_path: str, max_lines: int = 500) -> Dict[str, Any]:
        """Lê arquivo com limite de linhas."""
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": f"Arquivo não encontrado: {file_path}"}
        
        try:            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            truncated = len(lines) > max_lines
            content = ''.join(lines[:max_lines])
            
            return {
                "success": True,
                "file": file_path,
                "content": content,
                "total_lines": len(lines),
                "truncated": truncated,
                "action": "read"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def write_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Cria/sobrescreve arquivo."""
        if not file_path:
            return {"success": False, "error": "file_path não fornecido"}
        
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"[SurgicalEdit] Arquivo criado: {file_path}")
            return {
                "success": True,
                "file": file_path,
                "bytes": len(content),
                "action": "write"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        return True