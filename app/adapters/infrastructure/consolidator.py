# -*- coding: utf-8 -*-
"""Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense IA-Focused.
Versão 2026.1: Otimizada para Agentes Autônomos (Devin-like).
"""
import ast
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Set, Dict, Any

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

# Diretórios ignorados na consolidação
_IGNORED_DIRS: Set[str] = {
    ".git", "__pycache__", ".venv", "venv", "dist", "build", 
    "node_modules", ".github", ".frozen", "logs", "data", 
    ".backups", "tests", ".pytest_cache", ".idea", ".vscode", "assets"
}

# Extensões que a IA deve processar (Removido .md e .txt para evitar ruído)
_RELEVANT_EXT: Set[str] = {
    ".py", ".yml", ".yaml", ".json", ".dockerfile"
}

# Diretrizes Mestras que serão injetadas no topo do arquivo para orientar a IA
DIRETRIZES_MESTRAS = """
[DIRETRIZES MESTRAS DE OPERAÇÃO JARVIS]
1. ARQUITETURA: Respeite rigorosamente a Arquitetura Hexagonal (Domain, Application, Adapters).
2. INJEÇÃO: Use sempre o Nexus DI (nexus.resolve) para obter instâncias de componentes.
3. ESTADO: O PersistentShellAdapter mantém o estado do terminal; não reinicie processos desnecessariamente.
4. EDIÇÃO: Use o SurgicalEditService para modificações precisas em vez de reescrever arquivos.
5. MEMÓRIA: Consulte sempre a WorkingMemory para entender o progresso do ciclo Action-Observation.
"""

class Consolidator(NexusComponent):
    """Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense.
    
    Extrai a estrutura (skeleton) rica com docstrings e o conteúdo completo (dense)
    dos arquivos de código, ignorando documentações redundantes para humanos.
    """

    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"
        self.root_path = Path(".").resolve()

    def _get_layer_info(self, rel_path: str) -> str:
        """Determina a camada arquitetural baseada no path."""
        p = rel_path.lower().replace("\\", "/")
        if "app/core" in p: return "CORE (Motor/Nexus)"
        if "app/domain" in p: return "DOMAIN (Regras/Modelos)"
        if "app/application" in p: return "APPLICATION (Casos de Uso)"
        if "app/adapters" in p: return "ADAPTERS (Infra/IO)"
        return "SUPPORT (Config/Docs)"

    def _get_skeleton_with_docs(self, file_path: Path) -> str:
        """Gera skeleton de arquivos Python com extração de Docstrings."""
        if file_path.suffix != ".py":
            return "# (Skeleton disponível apenas para arquivos .py)"

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            skeleton = []

            for node in tree.body:
                # Extração de Classes e seus Métodos
                if isinstance(node, ast.ClassDef):
                    class_doc = ast.get_docstring(node)
                    skeleton.append(f"class {node.name}:")
                    if class_doc:
                        skeleton.append(f"    # DOC: {class_doc.splitlines()[0]}")
                    
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            func_doc = ast.get_docstring(item)
                            args = [a.arg for a in item.args.args]
                            skeleton.append(f"    def {item.name}({', '.join(args)}):")
                            if func_doc:
                                skeleton.append(f"        # DOC: {func_doc.splitlines()[0]}")
                
                # Extração de Funções Globais
                elif isinstance(node, ast.FunctionDef):
                    func_doc = ast.get_docstring(node)
                    args = [a.arg for a in node.args.args]
                    skeleton.append(f"def {node.name}({', '.join(args)}):")
                    if func_doc:
                        skeleton.append(f"    # DOC: {func_doc.splitlines()[0]}")

            return "\n".join(skeleton) if skeleton else "# (Nenhuma classe ou função definida)"
        except Exception as e:
            return f"# Erro ao gerar skeleton: {str(e)}"

    def _should_ignore(self, file_path: Path) -> bool:
        """Verifica se o arquivo deve ser ignorado."""
        parts = file_path.parts
        # Ignora arquivos de documentação humana no consolidado da IA
        if file_path.suffix in {".md", ".txt"} and file_path.name != "requirements.txt":
            return True
        return any(ignored in parts for ignored in _IGNORED_DIRS)

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Gera o snapshot consolidado otimizado para a inteligência do JARVIS."""
        logger.info("[NEXUS] Iniciando Consolidação IA-Focused")

        skeleton_sections = []
        content_sections = []

        all_files = [
            p for p in self.root_path.rglob("*") 
            if p.is_file() and p.suffix in _RELEVANT_EXT and not self._should_ignore(p)
        ]
        all_files.sort(key=lambda x: str(x))

        for file_path in all_files:
            try:
                rel_path = str(file_path.relative_to(self.root_path))
                layer = self._get_layer_info(rel_path)
                size = file_path.stat().st_size

                # Seção 1: Skeleton (Mapa de Intenções)
                skeleton_info = self._get_skeleton_with_docs(file_path)
                skeleton_sections.append(
                    f"[{layer}] {rel_path} ({size} bytes):\n{skeleton_info}\n" + "-"*30
                )

                # Seção 2: Dense (Código Fonte)
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

        # Escrita Final com Injeção de Diretrizes
        output_path = self.root_path / self.output_file
        with open(output_path, "w", encoding="utf-8") as out:
            out.write("=" * 80 + "\n")
            out.write("JARVIS CORE CONTEXT - AI-OPERATIONAL SNAPSHOT\n")
            out.write(f"TIMESTAMP: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            out.write(f"ROOT: {self.root_path}\n")
            out.write("=" * 80 + "\n")
            out.write(DIRETRIZES_MESTRAS)
            out.write("=" * 80 + "\n\n")

            out.write("SECTION 1 — INTENT SKELETON (ASSINATURAS & DOCSTRINGS)\n")
            out.write("=" * 80 + "\n")
            out.write("\n".join(skeleton_sections))
            out.write("\n\n" + "=" * 80 + "\n")
            out.write("SECTION 2 — DENSE CONTENT (CÓDIGO FONTE COMPLETO)\n")
            out.write("=" * 80 + "\n\n")
            out.write("".join(content_sections))

        logger.info(f"[NEXUS] Snapshot IA-Focused salvo em: {output_path}")

        res_payload = {
            "status": "success",
            "file_path": str(output_path),
            "files_processed": len(all_files),
        }
        context.setdefault("artifacts", {})["consolidator"] = res_payload
        return context
