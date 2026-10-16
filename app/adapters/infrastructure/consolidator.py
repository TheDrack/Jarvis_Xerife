# -*- coding: utf-8 -*-
"""Consolidador de Contexto JARVIS — Estratégia Skeleton-Dense.
CORREÇÃO: Mantido padrão original do CORE para compatibilidade com Nexus Discovery.
"""
import ast
import json
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
        """Gera o snapshot consolidado do repositório para integração do agente/LLM.

        O output usa 4 seções para dar ao agente ciência do que existe sem
        exigir leitura completa desnecessária:
          1. documentação e referencia do repo
          2. estrutura do repo (tree por camada)
          3. assinaturas e pontos de integracao (resumo leve)
          4. conteúdo consolidado dos arquivos relevantes

        Executa somente se passar do cooldown de 30 minutos, caso contrario
        retorna a ultima versão consolidada disponível.
        """
        logger.info("[CONSOLIDATOR] Verificando snapshot consolidado do repositório")

        # cooldown de 30 minutos entre execuções
        meta_path = self.root_path / "CORE_LOGIC_CONSOLIDATED.meta.json"
        now = datetime.now()
        last_run = None
        if meta_path.exists():
            try:
                last_run = datetime.fromisoformat(meta_path.read_text(encoding="utf-8").strip())
            except Exception:
                last_run = None

        cooldown_ok = False
        if last_run is None:
            cooldown_ok = True
        else:
            delta = (now - last_run).total_seconds()
            cooldown_ok = delta >= 30 * 60

        if not cooldown_ok:
            logger.info("[CONSOLIDATOR] Cooldown ativo. Retornando snapshot anterior.")
            ctx = context.copy()
            ctx["result"] = {
                "status": "cooldown",
                "message": "Snapshot consolidado em cooldown de 30 minutos.",
                "last_run": last_run.isoformat() if last_run else None,
                "file_path": str(self.output_file) if self.output_file and Path(self.output_file).exists() else None,
            }
            context.setdefault("artifacts", {}).setdefault("consolidator", ctx["result"])
            return context

        return self._generate_snapshot(context, now, meta_path)

    @staticmethod
    def _write_header(out, title: str) -> None:
        """Escreve o cabeçalho do documento com instruções de leitura.

        O documento é consumido por agentes/LLM, então precisa ser
        autoexplicativo: quem lê deve saber o que existe em cada seção sem
        abrir o repositório.
        """
        out.write("=" * 80 + "\n")
        out.write(title + "\n")
        out.write("=" * 80 + "\n\n")
        out.write("COMO LER ESTE DOCUMENTO\n")
        out.write("-" * 40 + "\n")
        out.write("- Seção 1: documentos de referência do repositório (DOCS_ORDER).\n")
        out.write("- Seção 2: árvore de arquivos agrupada por camada arquitetural.\n")
        out.write("- Seção 3: conteúdo consolidado dos arquivos relevantes.\n")
        out.write("- Seção 4: assinaturas (skeleton) e pontos de integração — apêndice.\n")
        out.write(
            "- Antes de criar ou editar código dependente, leia o arquivo "
            "original completo.\n"
        )
        out.write("\n")

    def _generate_snapshot(
        self, context: Dict[str, Any], now: datetime, meta_path: Path
    ) -> Dict[str, Any]:
        """Gera o snapshot consolidado e salva o meta de cooldown.

        Layout de saída: 1) documentação, 2) árvore, 3) conteúdo consolidado,
        4) assinaturas/assinaturas de integração (apêndice).
        """
        output_path = self.root_path / self.output_file

        all_files = [
            p for p in self.root_path.rglob("*")
            if p.is_file() and p.suffix in _RELEVANT_EXT
            and not self._should_ignore(p)
        ]
        all_files.sort(key=lambda x: str(x))

        logger.info(f"[CONSOLIDATOR] {len(all_files)} arquivos validados para processamento.")

        try:
            with open(output_path, "w", encoding="utf-8") as out:
                self._write_header(out, "CONSOLIDADOR JARVIS — REPOSITÓRIO PARA AGENTE/LLM")

                out.write("=" * 80 + "\n")
                out.write("SEÇÃO 1 — DOCUMENTAÇÃO DO PROJETO\n")
                out.write("=" * 80 + "\n\n")
                out.write("Documentos de referencia do repositório (DOCS_ORDER):\n\n")
                for doc in DOCS_ORDER:
                    out.write(f"- {doc}\n")
                out.write("\n" + "=" * 80 + "\n\n")

                out.write("=" * 80 + "\n")
                out.write("SEÇÃO 2 — ESTRUTURA DO PROJETO (TREE)\n")
                out.write("=" * 80 + "\n\n")
                for file_path in all_files:
                    rel_path = str(file_path.relative_to(self.root_path))
                    layer = self._get_layer_info(rel_path)
                    out.write(f"[{layer}] {rel_path}\n")
                out.write("\n" + "=" * 80 + "\n\n")

                # Seção 3: conteúdo consolidado, agrupado por camada. Vem antes
                # das assinaturas para que o leitor encontre o código completo
                # primeiro e use as assinaturas apenas como índice.
                out.write("=" * 80 + "\n")
                out.write("SEÇÃO 3 — CONTEÚDO DOS ARQUIVOS CONSOLIDADOS\n")
                out.write("=" * 80 + "\n\n")

                grouped: Dict[str, List[Path]] = {}
                for file_path in all_files:
                    rel_path = str(file_path.relative_to(self.root_path))
                    layer = self._get_layer_info(rel_path)
                    grouped.setdefault(layer, []).append(file_path)

                for layer in sorted(grouped.keys()):
                    out.write("#" * 80 + "\n")
                    out.write(f"CAMADA: {layer}\n")
                    out.write("#" * 80 + "\n")
                    for file_path in grouped[layer]:
                        rel_path = str(file_path.relative_to(self.root_path))
                        out.write("-" * 40 + "\n")
                        out.write(f"ARQUIVO: {rel_path}\n")
                        try:
                            content = file_path.read_text(encoding="utf-8", errors="replace")
                            content = self._compact_file_content(content, file_path)
                            out.write(content)
                            out.write("\n")
                        except Exception as exc:
                            out.write(f"# ERRO AO LER CONTEUDO: {exc}\n")
                        out.write("\n")
                    out.write("\n" + "=" * 80 + "\n\n")

                # Seção 4 (apêndice): assinaturas e pontos de integração
                out.write("=" * 80 + "\n")
                out.write("SEÇÃO 4 — ASSINATURAS E PONTOS DE INTEGRAÇÃO\n")
                out.write("=" * 80 + "\n\n")
                for file_path in all_files:
                    rel_path = str(file_path.relative_to(self.root_path))
                    out.write("-" * 80 + "\n")
                    out.write(f"ARQUIVO: {rel_path}\n")
                    out.write("-" * 80 + "\n")
                    if file_path.suffix == ".py":
                        summary = self._get_skeleton(file_path)
                        if summary.startswith("#"):
                            out.write(f"DETALHE: {summary}\n")
                        else:
                            out.write(summary + "\n")
                        out.write(
                            "INTEGRACAO: ler arquivo completo antes de criar/editar "
                            "codigo dependente.\n\n"
                        )
                    else:
                        size = file_path.stat().st_size
                        out.write(f"TIPO: {file_path.suffix} | TAMANHO: {size} bytes\n")
                        out.write("INTEGRACAO: ler arquivo completo antes de referenciar "
                                  "conteudo especializado.\n\n")

            logger.info(f"[CONSOLIDATOR] Snapshot consolidado gerado em: {output_path}")

            meta_payload = {
                "last_run": now.isoformat(),
                "file_path": str(output_path),
                "files_processed": len(all_files),
            }
            try:
                meta_path.write_text(
                    json.dumps(meta_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

            res_payload = {
                "status": "success",
                "file_path": str(output_path),
                "files_processed": len(all_files),
                "timestamp": now.isoformat(),
            }

            context.setdefault("artifacts", {})["consolidator"] = res_payload
            context["result"] = res_payload

        except Exception as exc:
            logger.error(f"[CONSOLIDATOR] Falha critica na gravacao: {exc}")
            context["result"] = {"status": "error", "message": str(exc)}

        return context

    def to_single_file_for_chat(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Gera um arquivo unico com as 4 seções juntas para envio no Telegram/LLM."""
        out_path = self.root_path / "CORE_LOGIC_CONSOLIDATED_FOR_CHAT.txt"

        all_files = [
            p for p in self.root_path.rglob("*")
            if p.is_file() and p.suffix in _RELEVANT_EXT
            and not self._should_ignore(p)
        ]
        all_files.sort(key=lambda x: str(x))

        try:
            with open(out_path, "w", encoding="utf-8") as out:
                self._write_header(out, "CONSOLIDADOR JARVIS — REPOSITORIO PARA AGENTE/LLM")

                out.write("SEÇÃO 1 — DOCUMENTAÇÃO DO PROJETO\n")
                out.write("-" * 40 + "\n")
                for doc in DOCS_ORDER:
                    out.write(f"- {doc}\n")
                out.write("\n")

                out.write("SEÇÃO 2 — ESTRUTURA DO PROJETO (TREE)\n")
                out.write("-" * 40 + "\n")
                for file_path in all_files:
                    rel = str(file_path.relative_to(self.root_path))
                    out.write(f"[{self._get_layer_info(rel)}] {rel}\n")
                out.write("\n")

                out.write("SEÇÃO 3 — CONTEÚDO DOS ARQUIVOS CONSOLIDADOS\n")
                out.write("-" * 40 + "\n")
                for file_path in all_files:
                    rel = str(file_path.relative_to(self.root_path))
                    out.write("#" * 80 + "\n")
                    out.write(f"ARQUIVO: {rel}\n")
                    try:
                        out.write(self._compact_file_content(
                            file_path.read_text(encoding="utf-8", errors="replace"),
                            file_path,
                        ))
                    except Exception as exc:
                        out.write(f"# ERRO AO LER CONTEUDO: {exc}\n")
                    out.write("\n")

                out.write("SEÇÃO 4 — ASSINATURAS E PONTOS DE INTEGRAÇÃO\n")
                out.write("-" * 40 + "\n")
                for file_path in all_files:
                    rel = str(file_path.relative_to(self.root_path))
                    out.write(f"ARQUIVO: {rel}\n")
                    if file_path.suffix == ".py":
                        out.write(self._get_skeleton(file_path) + "\n")
                    else:
                        out.write(f"TIPO: {file_path.suffix} | TAMANHO: {file_path.stat().st_size} bytes\n")
                out.write("\n")

            logger.info(f"[CONSOLIDATOR] Arquivo unico gerado em: {out_path}")
            context.setdefault("artifacts", {})["chat_export"] = {
                "status": "success",
                "file_path": str(out_path),
            }
            context["result"] = {
                "status": "success",
                "file_path": str(out_path),
                "purpose": "envio para telegram/llm",
            }
        except Exception as exc:
            logger.error(f"[CONSOLIDATOR] Falha critica na geração do chat export: {exc}")
            context["result"] = {"status": "error", "message": str(exc)}

        return context

    def _compact_file_content(self, content: str, file_path: Path, for_chat: bool = False) -> str:
        """Deixa o conteudo mais leve sem perder a organizacao."""
        if file_path.suffix == ".py":
            return content
        if for_chat:
            if len(content) > 2000:
                head = content[:1500]
                tail = content[-1500:]
                return head + "\n\n... conteudo reduzido para envio rapido (ler arquivo completo se necessaire) ...\n\n" + tail
        if len(content) > 8000:
            head = content[:4000]
            tail = content[-4000:]
            return head + "\n\n... conteudo adicional disponivel no arquivo original ...\n\n" + tail
        return content



# Documentos de referencia do repositório (usados pelo consolidador e pelo agente/LLM)
DOCS_ORDER = [
    "README.md",
    "ARCHITECTURE.md",
    "STATUS.md",
    "NEXUS.md",
    "ARQUIVO_MAP.md",
    "CONTRIBUTING.md",
    "SECURITY_GUARDRAILS.md",
    "Makefile",
    "Dockerfile",
    "render.yaml",
    ".env.example",
]


# Compatibilidade
Consolidate = Consolidator
