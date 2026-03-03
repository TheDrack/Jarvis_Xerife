# -*- coding: utf-8 -*-
import os
import logging
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
    Componente de Simbiose: Unifica o repositório com Documentação, Mapa de Árvore
    e Conteúdo de Código para otimização de contexto em LLMs.

    Estrutura do documento gerado:
        1. Cabeçalho + instruções de leitura para IA
        2. Documentação setorizada (README, arquitetura, Nexus, mapa de arquivos)
        3. Árvore de diretórios
        4. Conteúdo dos arquivos de código/config
    """

    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"

    def _write_doc_section(self, out, base_dir: str) -> None:
        """Inclui os arquivos de documentação setorizados no início do consolidado."""
        out.write("=" * 100 + "\n")
        out.write("SEÇÃO 1 — DOCUMENTAÇÃO DO PROJETO\n")
        out.write(
            "Esta seção contém a documentação humana do repositório: visão geral, arquitetura,\n"
            "padrões obrigatórios, mapa de componentes e status atual.\n"
            "Leia esta seção primeiro para entender o projeto antes de analisar o código-fonte.\n"
        )
        out.write("=" * 100 + "\n\n")

        for rel_path in DOCS_ORDER:
            abs_path = os.path.join(base_dir, rel_path)
            if not os.path.isfile(abs_path):
                continue
            label = rel_path.replace("\\", "/")
            out.write(f"\n{'─' * 80}\n")
            out.write(f"DOC: {label}\n")
            out.write(f"{'─' * 80}\n")
            try:
                with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    out.write(content if content.strip() else "[DOCUMENTO VAZIO]")
            except Exception as doc_error:
                out.write(f"[ERRO AO LER DOCUMENTO: {doc_error}]")
            out.write("\n")

    def execute(self, context: dict) -> dict:
        """
        Executa a consolidação e retorna o contexto atualizado com o caminho do arquivo.
        """
        print(f"🔬 [NEXUS] Iniciando Consolidação Estruturada: {datetime.now()}")

        # Configurações de Filtro
        ignored_dirs = {
            '.git', '__pycache__', '.venv', 'dist', 'build',
            'node_modules', 'venv', '.github',
        }
        relevant_extensions = (
            ".py", ".yml", ".yaml", ".json", ".sql",
            ".dockerfile", "Dockerfile", ".env.example",
        )

        try:
            # Garante caminho absoluto para evitar erros de localização em Cloud
            file_path = os.path.abspath(self.output_file)
            base_dir = os.getcwd()

            with open(file_path, "w", encoding="utf-8") as out:
                # 1. CABEÇALHO DE CONTEXTO PARA IA
                out.write("=" * 100 + "\n")
                out.write("PROJETO: JARVIS ASSISTANT — REPOSITÓRIO CONSOLIDADO\n")
                out.write(f"DATA DA EXTRAÇÃO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                out.write(
                    f"PIPELINE ORIGEM: {context.get('metadata', {}).get('pipeline', 'N/A')}\n"
                )
                out.write(
                    "OBJETIVO: Fornecer contexto completo, autodidático e estruturado do\n"
                    "repositório para que uma IA possa compreender arquitetura, padrões e\n"
                    "código sem conhecimento prévio.\n"
                    "\n"
                    "COMO LER ESTE DOCUMENTO:\n"
                    "  1. Seção 1 — Documentação: leia para entender propósito, arquitetura\n"
                    "     e padrões.\n"
                    "  2. Seção 2 — Árvore: veja a organização física dos arquivos.\n"
                    "  3. Seção 3 — Código: analise os arquivos-fonte e de configuração.\n"
                )
                out.write("=" * 100 + "\n\n")

                # 2. DOCUMENTAÇÃO SETORIZADA
                self._write_doc_section(out, base_dir)

                # 3. MAPA DA ÁRVORE DE DIRETÓRIOS
                out.write("\n" + "=" * 100 + "\n")
                out.write("SEÇÃO 2 — ESTRUTURA DO PROJETO (TREE)\n")
                out.write("=" * 100 + "\n")
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    level = root.replace('.', '').count(os.sep)
                    indent = ' ' * 4 * level
                    out.write(f"{indent}{os.path.basename(root)}/\n")
                    sub_indent = ' ' * 4 * (level + 1)

                    # Ordenação para manter consistência no Gist
                    for f in sorted(files):
                        if f.endswith(relevant_extensions) and f != self.output_file:
                            out.write(f"{sub_indent}📄 {f}\n")

                # 4. CONTEÚDO DOS ARQUIVOS DE CÓDIGO/CONFIG
                out.write("\n" + "=" * 100 + "\n")
                out.write("SEÇÃO 3 — CONTEÚDO DOS ARQUIVOS CONSOLIDADOS\n")
                out.write("=" * 100 + "\n")

                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    for file in sorted(files):
                        if file.endswith(relevant_extensions) and file != self.output_file:
                            path = os.path.join(root, file)

                            out.write(f"\n\nFILE_PATH: {path}\n")
                            out.write(f"FILE_NAME: {file}\n")
                            out.write("-" * 50 + "\n")

                            try:
                                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                    content = f.read()
                                    out.write(content if content.strip() else "[ARQUIVO VAZIO]")
                            except Exception as file_error:
                                out.write(f"[ERRO AO LER ARQUIVO: {file_error}]")

                            out.write(f"\n\n{'#'*70}\n")

            print(f"✅ [NEXUS] Consolidação técnica finalizada: {file_path}")

            # ATUALIZAÇÃO DO CONTEXTO: Fundamental para que Telegram/Gist funcionem
            res_payload = {
                "status": "success",
                "file_path": file_path,
                "timestamp": datetime.now().isoformat()
            }

            context["result"] = res_payload
            context["artifacts"]["consolidator"] = res_payload

            return context

        except Exception as e:
            print(f"💥 [CONSOLIDATOR] Erro Crítico: {e}")
            # Em caso de erro, o pipeline decide se para ou segue via strict_mode no runner
            raise e
