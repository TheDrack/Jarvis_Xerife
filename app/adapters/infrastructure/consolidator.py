# -*- coding: utf-8 -*-
"""Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense.
CORREÇÃO: Mantido padrão original do CORE para compatibilidade com Nexus Discovery.
"""
import ast
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Set, Dict, Any

try:
    from app.core.nexus import NexusComponent
except ImportError:
    class NexusComponent:
        def __init__(self):
            pass

logger = logging.getLogger(__name__)

_IGNORED_DIRS: Set[str] = {
    ".git", "__pycache__", ".venv", "venv", "dist", "build",
    "node_modules", ".github", ".frozen", "logs", "data",
    ".backups", "tests", ".pytest_cache", ".idea", ".vscode"
}

_RELEVANT_EXT: Set[str] = {
    ".py", ".yml", ".yaml", ".json", ".md", ".txt", ".dockerfile"
}


class Consolidator(NexusComponent):
    """Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense."""
    
    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"
        self.root_path = Path(".").resolve()
    
    def can_execute(self, context: Dict[str, Any] = None) -> bool:
        """NexusComponent contract."""
        return True
    
    def _get_layer_info(self, rel_path: str) -> str:
        """Determina a camada arquitetural baseada no path."""
        p = rel_path.lower().replace("\\", "/")
        if "app/core" in p:
            return "CORE (Motor/Nexus)"
        if "app/domain" in p:
            return "DOMAIN (Regras/Modelos)"
        if "app/application" in p:
            return "APPLICATION (Casos de Uso)"
        if "app/adapters" in p:
            return "ADAPTERS (Infra/IO)"
        return "SUPPORT (Config/Docs)"
    
    def _get_skeleton(self, file_path: Path) -> str:
        """Gera skeleton de arquivos Python (classes e funções)."""
        if file_path.suffix != ".py":
            return "# (Skeleton disponível apenas para arquivos .py)"
        
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
            skeleton = []
            
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    skeleton.append(f"class {node.name}:")
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            args = [a.arg for a in item.args.args[:3]]
                            skeleton.append(
                                f"    def {item.name}({', '.join(args)}...): ..."
                            )
                elif isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args[:3]]
                    skeleton.append(
                        f"def {node.name}({', '.join(args)}...): ..."
                    )
            
            return "\n".join(skeleton) if skeleton else "# (Nenhuma classe ou função detectada)"
        except SyntaxError:
            return "# Erro: Falha de sintaxe no arquivo original."
        except Exception as e:
            return f"# Erro ao gerar skeleton: {str(e)}"
    
    def _should_ignore(self, file_path: Path) -> bool:
        """Verifica se arquivo deve ser ignorado."""
        return any(part in _IGNORED_DIRS for part in file_path.parts)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Gera o snapshot consolidado de contexto."""
        logger.info("[NEXUS] Iniciando Consolidação Skeleton-Dense em modo Stream")
        
        skeleton_map = []
        output_path = self.root_path / self.output_file
        
        all_files = [
            p for p in self.root_path.rglob("*") 
            if p.is_file() and p.suffix in _RELEVANT_EXT
            and not self._should_ignore(p)
        ]
        all_files.sort(key=lambda x: str(x))
        
        logger.info(f"[NEXUS] {len(all_files)} arquivos validados para processamento.")
        
        try:
            with open(output_path, "w", encoding="utf-8") as out:
                # Seção 1: Skeleton Map
                for file_path in all_files:
                    rel_path = str(file_path.relative_to(self.root_path))
                    layer = self._get_layer_info(rel_path)
                    size = file_path.stat().st_size
                    skel = self._get_skeleton(file_path)
                    skeleton_map.append(
                        f"[{layer}] {rel_path} ({size} bytes):\n{skel}\n" + "-"*30
                    )
                
                out.write("SECTION 1 — STRUCTURAL SKELETON (MAPA DE ASSINATURAS)\n")
                out.write("=" * 80 + "\n")
                out.write("".join(skeleton_map))
                out.write("\n" + "=" * 80 + "\n")
                
                # Seção 2: Dense Content (Stream)
                out.write("SECTION 2 — DENSE CONTENT (CÓDIGO FONTE COMPLETO)\n")
                out.write("=" * 80 + "\n")
                
                for file_path in all_files:
                    rel_path = str(file_path.relative_to(self.root_path))
                    layer = self._get_layer_info(rel_path)
                    out.write(f"{'#'*80}\n")
                    out.write(f"# ARQUIVO: {rel_path}\n")
                    out.write(f"# CAMADA: {layer}\n")
                    out.write(f"{'#'*80}\n")
                    
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        out.write(content)
                        out.write("\n")
                    except Exception as e:
                        out.write(f"# ERRO AO LER CONTEÚDO: {str(e)}\n")
            
            logger.info(f"[NEXUS] Snapshot consolidado com sucesso em: {self.output_file}")
            
            res_payload = {
                "status": "success",
                "file_path": str(output_path),
                "files_processed": len(all_files),
                "timestamp": datetime.now().isoformat()            
            }
            
            context.setdefault("artifacts", {})["consolidator"] = res_payload
            context["result"] = res_payload
            
        except Exception as e:
            logger.error(f"[CONSOLIDATOR] Falha crítica na gravação: {e}")
            context["result"] = {"status": "error", "message": str(e)}
        
        return context


# Compatibilidade
Consolidate = Consolidator