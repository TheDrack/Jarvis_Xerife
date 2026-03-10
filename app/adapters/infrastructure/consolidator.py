# -*- coding: utf-8 -*-
"""
Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense.
Gera um snapshot do repositório otimizado para janelas de contexto longas.

Atualizado: 2026-03-10
- Removidas referências a .frozen/ (pasta não existe mais)
- Adicionados .md, .txt, .jrvs às extensões relevantes
- Adicionados logs, data aos diretórios ignorados
"""
import ast
import logging
import os
import re
from datetime import datetime
from typing import List

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

# Diretórios ignorados na consolidação
_IGNORED_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    "node_modules",
    ".github",
    ".frozen",  # Segurança: ignora se existir
    "logs",
    "data",
    ".backups",
}

# Extensões relevantes para consolidação
_RELEVANT_EXT = (
    ".py",    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".txt",
    ".dockerfile",
    ".jrvs",
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
    """Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense."""

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
            return "ADAPTERS (Infraestrutura/IO)"
        return "CONFIG/SUPPORT"

    def _get_skeleton(self, file_path: str) -> str:
        """Extrai a assinatura de classes e funções usando AST."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError:
                    return "[ERRO DE SINTAXE]"

            skeleton = []
            for node in ast.walk(tree):                if isinstance(node, ast.ClassDef):
                    skeleton.append(f"class {node.name}")
                elif isinstance(node, ast.FunctionDef):
                    skeleton.append(f"def {node.name}()")
            return " | ".join(skeleton[:10])  # Limita a 10 itens
        except Exception as e:
            logger.warning(f"Erro ao extrair skeleton de {file_path}: {e}")
            return "[ERRO]"

    def execute(self, context: dict) -> dict:
        """Gera o arquivo consolidado."""
        logger.info(f"📝 [NEXUS] Iniciando Consolidação Skeleton-Dense: {datetime.now()}")
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
                    if f.endswith(_RELEVANT_EXT) and f != "CORE_LOGIC_CONSOLIDATED.txt":
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, base_dir)
                        all_files.append((rel_path, full_path))

            # 1. Gera Skeleton (mapa estrutural)
            for rel_path, full_path in all_files:
                layer = self._get_layer_info(rel_path)
                skel_info = self._get_skeleton(full_path)
                skeleton_lines.append(f"[{layer}] {rel_path} -> {skel_info}")

            # 2. Gera Conteúdo Denso
            for rel_path, full_path in all_files:
                layer = self._get_layer_info(rel_path)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    content_lines.append(
                        f"{'#' * 80}\n"
                        f"ARQUIVO: {rel_path}\n"
                        f"CAMADA: {layer}\n"
                        f"{'#' * 80}\n"
                        f"{content}\n"                    )
                except Exception as e:
                    logger.warning(f"⚠️ [CONSOLIDATOR] Erro ao processar {rel_path}: {e}")
                    content_lines.append(f"[ERRO CRÍTICO NO ARQUIVO {rel_path}: {e}]\n")

            # Escrita Final
            with open(file_path, "w", encoding="utf-8") as out:
                # Header
                out.write("=" * 80 + "\n")
                out.write("JARVIS CONTEXT SNAPSHOT - ESTRATÉGIA SKELETON-DENSE\n")
                out.write(f"TIMESTAMP: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                out.write("PADRÃO: Arquitetura Hexagonal + Nexus DI\n")
                out.write("=" * 80 + "\n\n")

                # Seção 1: Mapa Estrutural
                out.write("SEÇÃO 1 — MAPA ESTRUTURAL (SKELETON)\n")
                out.write("-" * 40 + "\n")
                out.write("\n".join(skeleton_lines))
                out.write("\n\n")

                # Seção 2: Conteúdo Denso
                out.write("SEÇÃO 2 — CONTEÚDO DENSO (FULL LOGIC)\n")
                out.write("-" * 40 + "\n")
                out.write("\n".join(content_lines))

            logger.info(f"✅ [NEXUS] Consolidação técnica finalizada: {file_path}")

            # Atualiza contexto do Nexus
            res_payload = {
                "status": "success",
                "file_path": file_path,
                "timestamp": datetime.now().isoformat(),
                "files_processed": len(all_files),
            }
            context["result"] = res_payload
            context["artifacts"]["consolidator"] = res_payload

            return context

        except Exception as e:
            logger.error(f"💥 [CONSOLIDATOR] Falha na Homeostase do arquivo: {e}")
            raise e