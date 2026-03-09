# -*- coding: utf-8 -*-
import ast
import logging
import os
import re
from datetime import datetime
from typing import List, Set
from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

# Padrões de arquitetura para classificação automática
_ARCH_PATTERNS = {
    "CORE": [r"app/core", r"nexus", r"config"],
    "DOMAIN": [r"app/domain", r"models", r"services"],
    "APPLICATION": [r"app/application", r"ports", r"usecases"],
    "ADAPTERS": [r"app/adapters", r"infrastructure", r"edge"],
    "SUPPORT": [r"\.py$", r"\.yml", r"\.json", r"\.md"],
}

_IGNORED_DIRS = {
    ".git", "__pycache__", ".venv", "dist", "build", 
    "node_modules", ".github", ".frozen", "logs", "data"
}

_RELEVANT_EXT = (".py", ".yml", ".yaml", ".json", ".md", ".txt", ".dockerfile")

class Consolidator(NexusComponent):
    """
    Consolidador de Contexto JARVIS - Estratégia Skeleton-Dense.
    Gera um snapshot do repositório otimizado para janelas de contexto longas.
    """
    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"

    # ------------------------------------------------------------------
    # Helpers de Estrutura (AST)
    # ------------------------------------------------------------------
    def _get_skeleton(self, file_path: str) -> str:
        """Extrai a assinatura de classes e funções usando AST."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError:
                    return "[SyntaxError: Não foi possível parsear]"
            
            definitions = []
            for node in tree.body:                # Classes
                if isinstance(node, ast.ClassDef):
                    methods = [
                        n.name for n in node.body 
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    bases = ", ".join(b.id for b in node.bases if hasattr(b, 'id'))
                    definitions.append(f"Class {node.name}({bases}) :: [{', '.join(methods[:5])}]")
                # Funções de nível de módulo
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions.append(f"Def {node.name}()")
            
            return " | ".join(definitions) if definitions else "[Sem definições públicas]"
        except Exception as e:
            return f"[Erro AST: {str(e)}]"

    def _get_layer_info(self, path: str) -> str:
        """Classifica o arquivo baseado no caminho (Arquitetura Hexagonal)."""
        p = path.lower().replace("\\", "/")
        if any(re.search(pattern, p) for pattern in _ARCH_PATTERNS["CORE"]):
            return "CORE (Motor/Nexus)"
        if any(re.search(pattern, p) for pattern in _ARCH_PATTERNS["DOMAIN"]):
            return "DOMAIN (Regras de Negócio)"
        if any(re.search(pattern, p) for pattern in _ARCH_PATTERNS["APPLICATION"]):
            return "APPLICATION (Casos de Uso)"
        if any(re.search(pattern, p) for pattern in _ARCH_PATTERNS["ADAPTERS"]):
            return "ADAPTERS (Infra/IO)"
        return "SUPPORT (Config/Docs)"

    # ------------------------------------------------------------------
    # NexusComponent Interface
    # ------------------------------------------------------------------
    def execute(self, context: dict) -> dict:
        """Gera o arquivo consolidado."""
        logger.info(f" [NEXUS] Iniciando Consolidação Skeleton-Dense: {datetime.now()}")
        try:
            file_path = os.path.abspath(self.output_file)
            base_dir = os.getcwd()
            
            # Buffers de escrita
            skeleton_lines = []
            content_lines = []
            
            # Coleta de arquivos
            all_files = []
            for root, dirs, files in os.walk(base_dir):
                # Filtra diretórios ignorados
                dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
                for f in sorted(files):
                    if f.endswith(_RELEVANT_EXT) and f != self.output_file:                        all_files.append(os.path.join(root, f))

            # Processamento
            for path in all_files:
                try:
                    rel_path = os.path.relpath(path, base_dir)
                    layer = self._get_layer_info(rel_path)
                    
                    # 1. Gera Skeleton (apenas para Python)
                    skel_info = ""
                    if path.endswith('.py'):
                        skel_info = self._get_skeleton(path)
                        skeleton_lines.append(f"[{layer}] {rel_path} -> {skel_info}")
                    
                    # 2. Gera Conteúdo Denso
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    content_lines.append(f"\n{'#'*80}\nFILE: {rel_path}\nCAMADA: {layer}\n{'#'*80}\n{content}")
                    
                except Exception as e:
                    logger.warning(f" [CONSOLIDATOR] Erro ao processar {path}: {e}")
                    content_lines.append(f"\n[ERRO CRÍTICO NO ARQUIVO {path}: {e}]")

            # Escrita Final
            with open(file_path, "w", encoding="utf-8") as out:
                # Header
                out.write("=" * 80 + "\n")
                out.write("JARVIS CONTEXT SNAPSHOT - ESTRATÉGIA SKELETON-DENSE\n")
                out.write(f"TIMESTAMP: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                out.write("PADRÃO: Arquitetura Hexagonal + Nexus DI\n")
                out.write("=" * 80 + "\n\n")
                
                # Seção 1: Mapa
                out.write("SEÇÃO 1: MAPA ESTRUTURAL (SKELETON)\n")
                out.write("-" * 40 + "\n")
                out.write("\n".join(skeleton_lines))
                out.write("\n\n")
                
                # Seção 2: Conteúdo
                out.write("SEÇÃO 2: CONTEÚDO DENSO (FULL LOGIC)\n")
                out.write("-" * 40 + "\n")
                out.write("\n".join(content_lines))

            logger.info(f" [NEXUS] Consolidação técnica finalizada: {file_path}")
            
            # Atualiza contexto do Nexus
            context["result"] = {
                "status": "success", 
                "file_path": file_path,                 "timestamp": datetime.now().isoformat(),
                "files_processed": len(all_files)
            }
            context["artifacts"]["consolidator"] = context["result"]
            return context
            
        except Exception as e:
            logger.error(f" [CONSOLIDATOR] Falha na Homeostase do arquivo: {e}")
            raise e