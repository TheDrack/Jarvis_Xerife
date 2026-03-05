# -*- coding: utf-8 -*-
"""
evolution_mutator.py — Motor de mutação de capacidades do JARVIS.

Pipeline:
  1. Monta prompt rico com metadados da cap + exemplos de caps concluídas.
  2. Chama MetabolismCore (frota multi-LLM com fallback).
  3. Valida o código gerado em dois níveis: sintático (ast.parse) e semântico.
  4. Escreve o arquivo e marca o status como 'complete' apenas se passar.
"""
import argparse
import ast
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Adiciona o root do projeto ao path para imports locais
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.core.nexus import nexus
from app.utils.document_store import document_store


# ---------------------------------------------------------------------------
# Utilitários de dados
# ---------------------------------------------------------------------------

def _load_capabilities(cap_path: str = "data/capabilities.jrvs") -> List[Dict]:
    path = Path(cap_path)
    if not path.exists():
        return []
    return document_store.read(path).get("capabilities", [])


def _get_cap(cap_id: str, caps: List[Dict]) -> Optional[Dict]:
    for c in caps:
        if c["id"] == cap_id:
            return c
    return None


def _last_completed_examples(caps: List[Dict], n: int = 5) -> List[str]:
    """Retorna os conteúdos dos últimos n arquivos de caps completas."""
    completed = [c for c in caps if c.get("status") == "complete"]
    examples: List[str] = []
    for cap in completed[-n:]:
        num = cap["id"].replace("CAP-", "").zfill(3)
        file_path = Path(f"app/domain/capabilities/cap_{num}.py")
        if file_path.exists():
            code = file_path.read_text(encoding="utf-8")
            # Só usa como exemplo se não for um stub trivial
            if len(code.splitlines()) > 20 and "cap['id']" not in code:
                examples.append(f"### {cap['id']} — {cap.get('title', '')}\n{code}")
    return examples[-n:]


def _cap_id_to_class(cap_id: str) -> str:
    """CAP-042 → Cap042"""
    num = cap_id.replace("CAP-", "").zfill(3)
    return f"Cap{num}"


def _cap_id_to_file(cap_id: str) -> Path:
    num = cap_id.replace("CAP-", "").zfill(3)
    return Path(f"app/domain/capabilities/cap_{num}.py")


# ---------------------------------------------------------------------------
# Marcação de status
# ---------------------------------------------------------------------------

def update_capability_status(
    cap_id: str, status: str = "complete", cap_path: str = "data/capabilities.jrvs"
) -> bool:
    """Sincroniza o status no arquivo base de capacidades."""
    path = Path(cap_path)
    if not path.exists():
        print(f"⚠️  Alerta: {cap_path} não encontrado para atualização de status.")
        return False
    try:
        data = document_store.read(path)
        updated = False
        for cap in data.get("capabilities", []):
            if cap["id"] == cap_id:
                cap["status"] = status
                updated = True
                break
        if updated:
            document_store.write(path, data)
            print(f"💾 DNA Sincronizado: {cap_id} → {status}")
        return updated
    except Exception as exc:
        print(f"❌ Erro ao atualizar status: {exc}")
        return False


# ---------------------------------------------------------------------------
# Construção de prompts
# ---------------------------------------------------------------------------

_ARCHITECTURE_CONTRACT = """\
CONTRATO DE ARQUITETURA JARVIS:
- Toda capability herda de NexusComponent (de app.core.nexus).
- O arquivo deve ficar em app/domain/capabilities/.
- O método execute(self, context=None) NUNCA lança exceção — use try/except interno.
- execute() SEMPRE retorna um dict com ao menos {"success": bool}.
- Sem IO externo (sem requests, subprocess, open()) no corpo principal.
- Sem prints de debug.
- O código deve ser Python 3.9+ válido e completo.
"""

_RESPONSE_FORMAT = """\
FORMATO DE RESPOSTA:
Responda APENAS com um JSON válido no formato:
{"code": "<código Python completo>", "summary": "<1 frase descrevendo a implementação>"}
Não inclua markdown, comentários fora do JSON nem texto extra.
"""


def _build_prompts(cap: Dict, examples: List[str], roadmap_context: str) -> tuple:
    class_name = _cap_id_to_class(cap["id"])
    target_file = _cap_id_to_file(cap["id"])
    depends_str = ", ".join(cap.get("depends_on", [])) or "nenhuma"

    system_prompt = (
        "Você é o motor de auto-evolução do JARVIS, um assistente de IA distribuído.\n"
        f"{_ARCHITECTURE_CONTRACT}\n"
        f"{_RESPONSE_FORMAT}"
    )

    examples_block = ""
    if examples:
        joined = "\n\n".join(examples)
        examples_block = (
            f"\n\nEXEMPLOS DE CAPS JÁ CONCLUÍDAS (padrão esperado):\n{joined}"
        )

    user_prompt = (
        f"Implemente a seguinte capability:\n\n"
        f"ID: {cap['id']}\n"
        f"TÍTULO: {cap.get('title', '')}\n"
        f"DESCRIÇÃO: {cap.get('description', '')}\n"
        f"NOTAS/CAPÍTULO: {cap.get('notes', 'N/A')}\n"
        f"DEPENDÊNCIAS: {depends_str}\n"
        f"STATUS ATUAL: {cap.get('status', 'pending')}\n\n"
        f"NOME DA CLASSE ESPERADO: {class_name}\n"
        f"CAMINHO DO ARQUIVO: {target_file}\n\n"
        f"CONTEXTO DO ROADMAP: {roadmap_context or 'N/A'}"
        f"{examples_block}"
    )

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Validação em dois níveis
# ---------------------------------------------------------------------------

_TRIVIAL_MARKERS = [
    "print('🚀 Executando Cap",
    'print("🚀 Executando Cap',
    "return {'status': 'success', 'id': 'CAP-",
    'return {"status": "success", "id": "CAP-',
]

# Minimum number of real (non-docstring) statements required in execute()
_MIN_EXECUTE_STATEMENTS = 2


def _is_docstring(stmt: ast.stmt) -> bool:
    """Returns True if the AST statement is a bare string literal (docstring)."""
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)


def _count_real_statements(stmts: list) -> int:
    """Counts non-docstring statements in a function body."""
    return sum(1 for stmt in stmts if not _is_docstring(stmt))


def _validate_code(code: str) -> Optional[str]:
    """
    Retorna None se o código for válido; caso contrário retorna a razão da falha.
    """
    # Nível 1 — sintático
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"SyntaxError: {exc}"

    # Nível 2 — semântico
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if not classes:
        return "Nenhuma classe encontrada no código."

    has_execute = False
    execute_body_stmts = 0
    for cls in classes:
        for node in cls.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "execute":
                has_execute = True
                execute_body_stmts += _count_real_statements(node.body)

    if not has_execute:
        return "Método 'execute' não encontrado."
    if execute_body_stmts < _MIN_EXECUTE_STATEMENTS:
        return (
            f"O método execute() tem apenas {execute_body_stmts} statement(s) reais — "
            "implementação insuficiente."
        )

    for marker in _TRIVIAL_MARKERS:
        if marker in code:
            return f"Código contém marcador de stub trivial: {marker!r}"

    return None  # Válido


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def _evolve_cap(
    cap_id: str,
    roadmap_context: str,
    max_attempts: int,
    caps: List[Dict],
) -> bool:
    """
    Executa o pipeline completo para uma cap.
    Retorna True em sucesso, False em falha definitiva.
    """
    cap = _get_cap(cap_id, caps)
    if not cap:
        print(f"❌ {cap_id} não encontrado em capabilities.jrvs")
        return False

    examples = _last_completed_examples(caps)
    target_file = _cap_id_to_file(cap_id)
    core = nexus.resolve("metabolism_core")
    if core is None:
        print(
            f"❌ [{cap_id}] Nexus não conseguiu resolver 'metabolism_core'. "
            "Verifique as dependências e o ambiente."
        )
        return False

    system_prompt, user_prompt = _build_prompts(cap, examples, roadmap_context)
    failure_reason: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        current_user_prompt = user_prompt
        if failure_reason and attempt > 1:
            current_user_prompt = (
                f"{user_prompt}\n\n"
                f"TENTATIVA {attempt}/{max_attempts} — A tentativa anterior falhou por:\n"
                f"{failure_reason}\n"
                "Corrija o problema e retorne um código válido."
            )

        print(f"🧬 [{cap_id}] Tentativa {attempt}/{max_attempts}...")
        try:
            response = core.ask_jarvis(system_prompt, current_user_prompt, require_json=True)
        except Exception as exc:
            print(f"   ❌ LLM falhou: {exc}")
            failure_reason = str(exc)
            continue

        if isinstance(response, dict):
            code = response.get("code", "")
            summary = response.get("summary", "")
        else:
            code = str(response)
            summary = ""

        if not code:
            failure_reason = "Resposta do LLM não continha campo 'code'."
            print(f"   ⚠️  {failure_reason}")
            continue

        failure_reason = _validate_code(code)
        if failure_reason:
            print(f"   ⚠️  Validação falhou: {failure_reason}")
            continue

        # Validação passou — escrever o arquivo
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(code, encoding="utf-8")
        print(f"   ✅ {target_file} escrito com sucesso.")
        if summary:
            print(f"   📝 Resumo: {summary}")

        update_capability_status(cap_id, "complete")
        return True

    print(f"❌ [{cap_id}] Todas as {max_attempts} tentativas falharam.")
    return False


# ---------------------------------------------------------------------------
# Função pública chamável por outros scripts
# ---------------------------------------------------------------------------

def evolve(
    cap_id: Optional[str] = None,
    roadmap_context: str = "",
    max_attempts: int = 3,
) -> bool:
    """
    Entry-point para uso programático (ex: evolve_all_pending.py).
    Retorna True se a evolução foi bem-sucedida.
    """
    caps = _load_capabilities()
    if not cap_id:
        # Tenta extrair do ISSUE_BODY
        issue_body = os.getenv("ISSUE_BODY", "")
        m = re.search(r"(CAP-\d+)", issue_body)
        if m:
            cap_id = m.group(1)
    if not cap_id:
        print("❌ cap_id não informado.")
        return False
    return _evolve_cap(cap_id, roadmap_context, max_attempts, caps)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Motor de mutação de capacidades JARVIS")
    parser.add_argument("--cap-id", help="Ex: CAP-042")
    parser.add_argument("--roadmap-context", default="", help="Contexto livre do roadmap")
    parser.add_argument("--max-attempts", type=int, default=3)
    # Compatibilidade com Actions legado
    parser.add_argument("--strategy", default="")
    parser.add_argument("--intent", default="")
    parser.add_argument("--impact", default="")

    args = parser.parse_args()

    cap_id = args.cap_id
    if not cap_id:
        issue_body = os.getenv("ISSUE_BODY", "")
        m = re.search(r"(CAP-\d+)", issue_body)
        if m:
            cap_id = m.group(1)
    if not cap_id and args.roadmap_context:
        m = re.search(r"(CAP-\d+)", args.roadmap_context)
        if m:
            cap_id = m.group(1)
    if not cap_id:
        print("❌ Erro: CAP-ID não encontrado. Use --cap-id ou defina ISSUE_BODY.")
        sys.exit(1)

    success = evolve(cap_id=cap_id, roadmap_context=args.roadmap_context, max_attempts=args.max_attempts)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

