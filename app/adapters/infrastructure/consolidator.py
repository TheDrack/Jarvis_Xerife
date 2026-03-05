# -*- coding: utf-8 -*-
import os
import logging
import re
from datetime import datetime
from app.core.nexuscomponent import NexusComponent

# Configuração de logging integrada ao Nexus
logger = logging.getLogger(__name__)

# Arquivos de documentação incluídos no início do consolidado para prover contexto geral
DOCS_ORDER = [
    "README.md",
    "padrão_estrutural.md",
    "docs/STATUS.md",
    "docs/ARCHITECTURE.md",
    "docs/NEXUS.md",
    "docs/ARQUIVO_MAP.md",
]

class Consolidator(NexusComponent):
    """
    Componente de Simbiose Evoluído: Unifica o repositório com metadados estruturais.
    Implementa mapeamento de dependências e análise de camadas para otimização de LLMs.
    """

    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"
        self.component_map = {} # Nome -> Path para cross-reference

    def _get_layer_info(self, path: str) -> str:
        """Define a responsabilidade arquitetural baseada no path."""
        path_lower = path.lower()
        if "app/core" in path_lower:
            return "CORE (Motor do Sistema/Nexus): Infraestrutura crítica e DI."
        if "app/domain" in path_lower:
            return "DOMAIN (Regras de Negócio): Lógica pura, independente de IO."
        if "app/application" in path_lower:
            return "APPLICATION (Casos de Uso): Orquestração e Portas (Interfaces)."
        if "app/adapters" in path_lower:
            return "ADAPTERS (Infraestrutura/IO): Implementações externas (GitHub, APIs, Hardware)."
        return "CONFIG/SUPPORT: Arquivos de configuração ou suporte."

    def _extract_dependencies(self, content: str) -> list:
        """Detecta chamadas ao Nexus e imports internos."""
        deps = re.findall(r'nexus\.resolve\(["\']([^"\']+)["\']\)', content)
        return sorted(list(set(deps)))

    def _write_doc_section(self, out, base_dir: str) -> None:
        """Inclui os arquivos de documentação setorizados."""
        out.write("\n" + "=" * 100 + "\n")
        out.write("SEÇÃO 1 — DOCUMENTAÇÃO DO PROJETO\n")
        out.write("=" * 100 + "\n\n")

        for rel_path in DOCS_ORDER:
            abs_path = os.path.join(base_dir, rel_path)
            if not os.path.isfile(abs_path): continue
            out.write(f"\n{'─' * 80}\nDOC: {rel_path.replace('\\', '/')}\n{'─' * 80}\n")
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    out.write(f.read() or "[DOCUMENTO VAZIO]")
            except Exception as e:
                out.write(f"[ERRO AO LER: {e}]")
            out.write("\n")

    def execute(self, context: dict) -> dict:
        print(f" [NEXUS] Iniciando Consolidação Simbiótica: {datetime.now()}")

        ignored_dirs = {'.git', '__pycache__', '.venv', 'dist', 'build', 'node_modules', '.github'}
        relevant_extensions = (".py", ".yml", ".yaml", ".json", ".sql", ".dockerfile", "Dockerfile")

        try:
            file_path = os.path.abspath(self.output_file)
            base_dir = os.getcwd()

            with open(file_path, "w", encoding="utf-8") as out:
                # 1. CABEÇALHO DE ALTA FIDELIDADE
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
                out.write("SEÇÃO 3: Conteúdo dos arquivos do projeto\n\n")

                # 2. DOCUMENTAÇÃO
                self._write_doc_section(out, base_dir)

                # 3. ESTRUTURA E MAPA DE COMPONENTES
                out.write("\n" + "=" * 100 + "\n")
                out.write("SEÇÃO 2 — ESTRUTURA DO PROJETO (TREE)\n")
                out.write("=" * 100 + "\n")
                
                all_files = []
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    for f in sorted(files):
                        if f.endswith(relevant_extensions) and f != self.output_file:
                            full_path = os.path.join(root, f)
                            all_files.append(full_path)
                            # Adiciona árvore textual simplificada
                            level = root.replace('.', '').count(os.sep)
                            out.write(f"{' ' * 4 * level} {full_path}\n")

                # 4. CONTEÚDO ANALÍTICO
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
                        
                        out.write(content if content.strip() else "[ARQUIVO VAZIO]")
                        out.write(f"\n\n{'#' * 80}\n")

                    except Exception as e:
                        out.write(f"\n[ERRO CRÍTICO NO ARQUIVO {path}: {e}]\n")

            print(f" [NEXUS] Consolidação técnica finalizada: {file_path}")
            
            res_payload = {"status": "success", "file_path": file_path, "timestamp": datetime.now().isoformat()}
            context["result"] = res_payload
            context["artifacts"]["consolidator"] = res_payload

            return context

        except Exception as e:
            print(f" [CONSOLIDATOR] Falha na Homeostase do arquivo: {e}")
            raise e