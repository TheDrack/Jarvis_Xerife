# -*- coding: utf-8 -*-
"""Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense.
CORRIGIDO: Varredura recursiva de subdiretórios aninhados.
"""
import ast
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Set

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

# Ordem de documentação no consolidado
DOCS_ORDER = [
    "README.md",
    "padrão_estrutural.md",
    "docs/STATUS.md",
    "docs/ARCHITECTURE.md",
    "docs/NEXUS.md",
    "docs/ARQUIVO_MAP.md",
]

# Diretórios ignorados na consolidação (COMPARAÇÃO EXATA DE PATH)
_IGNORED_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "node_modules",
    ".github",
    ".frozen",
    "logs",
    "data",
    ".backups",
    "tests",  # Opcional: ignorar testes para reduzir tamanho
}

# Extensões relevantes para consolidação
_RELEVANT_EXT: tuple = (
    ".py",
    ".yml",
    ".yaml",
    ".json",
    ".md",    ".txt",
    ".dockerfile",
)

# Padrões de camadas arquiteturais
_ARCH_PATTERNS = {
    "CORE": [r"app/core", r"nexus"],
    "DOMAIN": [r"app/domain", r"capabilities", r"services", r"models"],
    "APPLICATION": [r"app/application", r"ports", r"usecases"],
    "ADAPTERS": [r"app/adapters", r"infrastructure", r"edge"],
    "SUPPORT": [r"\.py$", r"\.yml", r"\.json", r"\.md"],
}


class Consolidator(NexusComponent):
    """Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense.
    
    CORRIGIDO: Agora varre corretamente subdiretórios aninhados como:
    - app/application/services/jarvis_dev_agent/
    - app/application/services/jarvis_dev_agent/*.py
    """
    
    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"
    
    def _get_layer_info(self, path: str) -> str:
        """Determina a camada arquitetural de um arquivo."""
        p = path.lower()
        if "app/core" in p:
            return "CORE (Motor/Nexus)"
        if "app/domain" in p:
            return "DOMAIN (Regras de Negócio)"
        if "app/application" in p:
            return "APPLICATION (Casos de Uso)"
        if "app/adapters" in p:
            return "ADAPTERS (Infra/IO)"
        return "SUPPORT (Config/Docs)"
    
    def _get_skeleton(self, file_path: str) -> str:
        """Gera skeleton de um arquivo (apenas assinatura)."""
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            skeleton = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    skeleton.append(f"class {node.name}:")
                elif isinstance(node, ast.FunctionDef):                    args = ", ".join(arg.arg for arg in node.args.args[:3])
                    skeleton.append(f"def {node.name}({args}): ...")
            
            return "\n".join(skeleton[:20])  # Limita a 20 linhas
        except Exception as e:
            return f"# Erro ao gerar skeleton: {e}"
    
    def _should_ignore(self, file_path: Path) -> bool:
        """
        Verifica se arquivo deve ser ignorado.
        
        CORRIGIDO: Usa comparação de partes do path, não substring.
        """
        # Converte para partes do path
        parts = set(file_path.parts)
        path_str = str(file_path)
        
        # Verifica se alguma parte do path está na lista de ignorados
        for ignored in _IGNORED_DIRS:
            if ignored in parts:  # Comparação exata de partes
                return True
            
            # Também verifica se é um diretório completo no path
            if f"/{ignored}/" in path_str or path_str.startswith(f"{ignored}/"):
                return True
        
        return False
    
    def execute(self, context: dict) -> dict:
        """Gera o arquivo consolidado.
        
        CORRIGIDO: Varredura recursiva completa de todos os subdiretórios.
        """
        logger.info("[NEXUS] Iniciando Consolidação Skeleton-Dense")
        
        skeleton_lines = []
        content_lines = []
        
        # Varre TODOS os arquivos relevantes recursivamente
        all_files = []
        for pattern in _RELEVANT_EXT:
            # rglob é recursivo infinito
            for file_path in Path(".").rglob(f"*{pattern}"):
                if not self._should_ignore(file_path):
                    all_files.append(file_path)
        
        # Remove duplicatas e ordena
        all_files = sorted(set(all_files), key=lambda p: str(p))
        
        logger.info(f"[NEXUS] {len(all_files)} arquivos encontrados para consolidação")        
        # Processa cada arquivo
        for file_path in all_files:
            try:
                rel_path = str(file_path.relative_to(Path(".").resolve()))
                layer = self._get_layer_info(rel_path)
                size = file_path.stat().st_size
                
                # Adiciona ao skeleton
                skeleton_lines.append(f"[{layer}] {rel_path} ({size} bytes)\n")
                
                # Adiciona conteúdo completo
                content = file_path.read_text(encoding="utf-8")
                content_lines.append(f"\n{'#'*80}\n")
                content_lines.append(f"# ARQUIVO: {rel_path}\n")
                content_lines.append(f"# CAMADA: {layer}\n")
                content_lines.append(f"{'#'*80}\n\n")
                content_lines.append(content)
                content_lines.append("\n\n")
                
            except Exception as e:
                logger.error(f"[CONSOLIDATOR] Erro ao processar {file_path}: {e}")
                content_lines.append(f"[ERRO CRÍTICO NO ARQUIVO {file_path}: {e}]\n")
        
        # Escreve arquivo consolidado
        file_path = Path(self.output_file)
        with open(file_path, "w", encoding="utf-8") as out:
            out.write("=" * 80 + "\n")
            out.write("JARVIS CONTEXT SNAPSHOT - ESTRATÉGIA SKELETON-DENSE\n")
            out.write(f"TIMESTAMP: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            out.write("PADRÃO: Arquitetura Hexagonal + Nexus DI\n")
            out.write("=" * 80 + "\n\n")
            
            out.write("SEÇÃO 1 — MAPA ESTRUTURAL (SKELETON)\n")
            out.write("-" * 40 + "\n")
            out.write("".join(skeleton_lines))
            out.write("\n")
            
            out.write("SEÇÃO 2 — CONTEÚDO DENSO (FULL LOGIC)\n")
            out.write("-" * 40 + "\n")
            out.write("".join(content_lines))
        
        logger.info(f"[NEXUS] Consolidação finalizada: {file_path}")
        
        res_payload = {
            "status": "success",
            "file_path": str(file_path),
            "timestamp": datetime.now().isoformat(),
            "files_processed": len(all_files),
        }        
        context["result"] = res_payload
        context["artifacts"]["consolidator"] = res_payload
        
        return context