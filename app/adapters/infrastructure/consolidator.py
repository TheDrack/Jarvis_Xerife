# -*- coding: utf-8 -*-
"""Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense."""
import ast
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Set, Dict, Any
from app.core.nexus import NexusComponent

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
        """NexusComponent contract — verifica se pode executar."""
        return True
    
    def configure(self, config: Dict[str, Any] = None) -> None:
        """Opcional: Configuração via Pipeline YAML."""
        if config:
            pass
    
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
            
            return "\n".join(skeleton) if skeleton else "# (Nenhuma classe ou função)"
            
        except Exception as e:
            return f"# Erro ao gerar skeleton: {str(e)}"
    
    def _should_ignore(self, file_path: Path) -> bool:
        """Verifica se arquivo deve ser ignorado."""
        parts = file_path.parts
        return any(ignored in parts for ignored in _IGNORED_DIRS)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gera o snapshot consolidado de contexto.
        
        Atualiza:
        - context["result"]["file_path"]
        - context["artifacts"]["consolidator"]
        """
        logger.info("[NEXUS] Iniciando Consolidação Skeleton-Dense")
        
        skeleton_sections = []
        content_sections = []        
        
        # Coleta de arquivos em uma única passada
        all_files = [
            p for p in self.root_path.rglob("*")
            if p.is_file() and p.suffix in _RELEVANT_EXT
            and not self._should_ignore(p)
        ]
        all_files.sort(key=lambda x: str(x))
        
        logger.info(f"[NEXUS] {len(all_files)} arquivos validados para processamento.")
        
        for file_path in all_files:
            try:
                rel_path = str(file_path.relative_to(self.root_path))
                layer = self._get_layer_info(rel_path)
                size = file_path.stat().st_size
                
                # Seção 1: Skeleton
                skeleton_info = self._get_skeleton(file_path)
                skeleton_sections.append(
                    f"[{layer}] {rel_path} ({size} bytes):\n{skeleton_info}\n" + "-"*30
                )
                
                # Seção 2: Conteúdo completo
                content = file_path.read_text(encoding="utf-8", errors="replace")
                content_sections.append(
                    f"{'#'*80}\n"
                    f"# ARQUIVO: {rel_path}\n"
                    f"# CAMADA: {layer}\n"
                    f"{'#'*80}\n\n"
                    f"{content}\n\n"
                )
                
            except Exception as e:
                logger.error(f"[CONSOLIDATOR] Erro em {file_path}: {e}")
        
        # Escrita do arquivo físico
        output_path = self.root_path / self.output_file
        with open(output_path, "w", encoding="utf-8") as out:
            out.write("=" * 80 + "\n")
            out.write("JARVIS CONTEXT SNAPSHOT - SKELETON-DENSE STRATEGY\n")
            out.write(f"TIMESTAMP: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            out.write(f"ROOT: {self.root_path}\n")
            out.write("=" * 80 + "\n\n")
            
            out.write("SECTION 1 — STRUCTURAL SKELETON (MAPA DE ASSINATURAS)\n")
            out.write("=" * 80 + "\n")
            out.write("\n".join(skeleton_sections))
            out.write("\n\n" + "=" * 80 + "\n")
            
            # CORREÇÃO: Linhas separadas para evitar SyntaxError
            out.write("SECTION 2 — DENSE CONTENT (CÓDIGO FONTE COMPLETO)\n")
            out.write("=" * 80 + "\n\n")
            
            out.write("".join(content_sections))
        
        logger.info(f"[NEXUS] Snapshot salvo em: {output_path}")
        
        # CRÍTICO: Atualiza contexto para pipeline
        res_payload = {
            "status": "success",
            "file_path": str(output_path),
            "files_processed": len(all_files),
        }
        
        # Atualiza context["artifacts"]["consolidator"]
        context.setdefault("artifacts", {})["consolidator"] = res_payload
        
        # Atualiza context["result"]
        context["result"] = res_payload
        
        return context
