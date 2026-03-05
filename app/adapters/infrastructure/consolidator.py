# -*- coding: utf-8 -*-
import ast
import logging
import os
import re
from datetime import datetime
from typing import List

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

DOCS_ORDER = [
    "README.md",
    "padrão_estrutural.md",
    "docs/STATUS.md",
    "docs/ARCHITECTURE.md",
    "docs/NEXUS.md",
    "docs/ARQUIVO_MAP.md",
]
_IGNORED_DIRS = {".git", "__pycache__", ".venv", "dist", "build", "node_modules", ".github"}
_RELEVANT_EXT = (".py", ".yml", ".yaml", ".json", ".sql", ".dockerfile", "Dockerfile")

class Consolidator(NexusComponent):
    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_layer_info(self, path: str) -> str:
        p = path.lower()
        if "app/core" in p:
            return "CORE (Motor do Sistema/Nexus): Infraestrutura crítica e DI."
        if "app/domain" in p:
            return "DOMAIN (Regras de Negócio): Lógica pura, independente de IO."
        if "app/application" in p:
            return "APPLICATION (Casos de Uso): Orquestração e Portas (Interfaces)."
        if "app/adapters" in p:
            return "ADAPTERS (Infraestrutura/IO): Implementações externas (GitHub, APIs, Hardware)."
        return "CONFIG/SUPPORT: Arquivos de configuração ou suporte."

    def _extract_dependencies(self, content: str) -> List[str]:
        deps = re.findall(r'nexus\.resolve\(["\']([^"\']+)["\']\)', content)
        return sorted(set(deps))

    @staticmethod
    def _is_test_file(path: str) -> bool:
        """Return True when *path* is a pytest test file (in tests/ or named test_*.py)."""
        norm = path.replace("\\", "/")
        return os.path.basename(path).startswith("test_") or "/tests/" in norm

    @staticmethod
    def _summarize_test_file(content: str) -> str:
        """Extract test names from *content* and return a compact summary string."""
        try:
            tree = ast.parse(content)
            funcs = []
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    funcs.append(node.name)
                elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    classes.append(node.name)
        except SyntaxError:
            funcs = re.findall(r"def (test_\w+)", content)
            classes = re.findall(r"class (Test\w+)", content)

        lines = [f"[RESUMO DE TESTES — {len(funcs)} funções de teste]"]
        if classes:
            lines.append(f"Classes: {', '.join(classes)}")
        lines.extend(f"  - {fn}" for fn in funcs)
        return "\n".join(lines)

    def _write_doc_section(self, out, base_dir: str) -> None:
        out.write("\n" + "=" * 100 + "\n")
        out.write("SEÇÃO 1 — DOCUMENTAÇÃO DO PROJETO\n")
        out.write("=" * 100 + "\n\n")
        for rel_path in DOCS_ORDER:
            abs_path = os.path.join(base_dir, rel_path)
            if not os.path.isfile(abs_path):
                continue
            out.write(f"\n{'─' * 80}\nDOC: {rel_path.replace('\\', '/')}\n{'─' * 80}\n")
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    out.write(f.read() or "[DOCUMENTO VAZIO]")
            except Exception as e:
                out.write(f"[ERRO AO LER: {e}]")
            out.write("\n")

    # ------------------------------------------------------------------
    # NexusComponent execute
    # ------------------------------------------------------------------

    def execute(self, context: dict) -> dict:
        print(f" [NEXUS] Iniciando Consolidação Simbiótica: {datetime.now()}")
        try:
            file_path = os.path.abspath(self.output_file)
            base_dir = os.getcwd()

            with open(file_path, "w", encoding="utf-8") as out:
                out.write("=" * 100 + "\n")
                out.write("JARVIS ASSISTANT - CONTEXTO SIMBIÓTICO DE ALTO NÍVEL\n")
                out.write(f"TIMESTAMP: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                out.write("PADRÃO: Arquitetura Hexagonal + Nexus DI\n")
                out.write("=" * 100 + "\n\n")
                out.write("COMO LER ESTE DOCUMENTO\n")
                out.write("-" * 40 + "\n")
                out.write("Este documento está organizado em 3 seções:\n")
                out.write("SEÇÃO 1: Documentação (README, arquitetura, etc.)\n")
                out.write("SEÇÃO 2: Estrutura de diretórios (tree)\n")
                out.write("SEÇÃO 3: Conteúdo dos arquivos (testes exibidos como resumo)\n\n")

                self._write_doc_section(out, base_dir)

                out.write("\n" + "=" * 100 + "\n")
                out.write("SEÇÃO 2 — ESTRUTURA DO PROJETO (TREE)\n")
                out.write("=" * 100 + "\n")

                all_files = []
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
                    for f in sorted(files):
                        if f.endswith(_RELEVANT_EXT) and f != self.output_file:
                            full_path = os.path.join(root, f)
                            all_files.append(full_path)
                            level = root.replace(".", "").count(os.sep)
                            out.write(f"{' ' * 4 * level} {full_path}\n")

                out.write("\n" + "=" * 100 + "\n")
                out.write("SEÇÃO 3 — CONTEÚDO DOS ARQUIVOS CONSOLIDADOS\n")
                out.write("=" * 100 + "\n")

                for path in all_files:
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        layer = self._get_layer_info(path)
                        deps = self._extract_dependencies(content)

                        out.write(f"\n\n{'#' * 80}\n")
                        out.write(f"ARQUIVO: {path}\n")
                        out.write(f"CAMADA: {layer}\n")
                        if deps:
                            out.write(f"DEPENDÊNCIAS NEXUS: {', '.join(deps)}\n")
                        out.write(f"{'-' * 80}\n\n")

                        if self._is_test_file(path):
                            out.write(self._summarize_test_file(content))
                        else:
                            out.write(content if content.strip() else "[ARQUIVO VAZIO]")
                        out.write(f"\n\n{'#' * 80}\n")

                    except Exception as e:
                        out.write(f"\n[ERRO CRÍTICO NO ARQUIVO {path}: {e}]\n")

            print(f" [NEXUS] Consolidação técnica finalizada: {file_path}")
            res_payload = {
                "status": "success",
                "file_path": file_path,
                "timestamp": datetime.now().isoformat(),
            }
            context["result"] = res_payload
            context["artifacts"]["consolidator"] = res_payload
            return context

        except Exception as e:
            print(f" [CONSOLIDATOR] Falha na Homeostase do arquivo: {e}")
            raise e