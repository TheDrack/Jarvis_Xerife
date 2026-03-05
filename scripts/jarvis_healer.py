# -*- coding: utf-8 -*-
import argparse
import json
import os
import subprocess
import re
import requests
from pathlib import Path

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def _has_failures(report_path: str) -> bool:
    """
    Read the pytest-json-report file and return True only when there are
    actual test failures or collection errors that require healing.
    Returns True (conservative/safe) when the file is absent or unparseable.
    """
    if not report_path or not os.path.exists(report_path):
        return True  # No report → assume failures to be safe
    try:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        summary = data.get("summary", {})
        return bool(summary.get("failed", 0) or summary.get("error", 0))
    except Exception:
        return True  # Can't parse → assume failures to be safe


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes add despite instructions."""
    # Remove opening fence: ```python or ```
    text = re.sub(r'^```[a-zA-Z]*\s*\n?', '', text.strip())
    # Remove closing fence
    text = re.sub(r'\n?```\s*$', '', text.strip())
    return text.strip()


def _strip_injected_test_code(source: str) -> str:
    """
    Remove pytest imports and test functions injected by the LLM into production files.
    Uses the ast module for reliable multi-line handling. Falls back to regex on parse failure.
    """
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _strip_injected_test_code_regex(source)

    lines = source.splitlines(keepends=True)
    lines_to_remove: set = set()

    # Only inspect top-level nodes (module body) to avoid stripping nested helpers
    for node in tree.body:
        # Remove: import pytest  /  from pytest import ...
        if isinstance(node, ast.Import):
            if any(alias.name == "pytest" or alias.name.startswith("pytest.") for alias in node.names):
                for ln in range(node.lineno, node.end_lineno + 1):
                    lines_to_remove.add(ln)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "pytest" or node.module.startswith("pytest.")):
                for ln in range(node.lineno, node.end_lineno + 1):
                    lines_to_remove.add(ln)
        # Remove top-level test functions (sync and async) together with their decorators
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
                for ln in range(start, node.end_lineno + 1):
                    lines_to_remove.add(ln)

    result = "".join(line for i, line in enumerate(lines, start=1) if i not in lines_to_remove)
    return result.strip()


def _strip_injected_test_code_regex(source: str) -> str:
    """Regex fallback for _strip_injected_test_code when ast.parse fails."""
    # Remove all variants of pytest imports
    source = re.sub(r'^(?:import pytest[^\n]*|from pytest[^\n]*)\n', '', source, flags=re.MULTILINE)
    # Remove @pytest.mark.* decorator lines
    source = re.sub(r'^@pytest\.[^\n]+\n', '', source, flags=re.MULTILINE)
    # Remove test function header + indented body (greedy up to next top-level def/class or EOF)
    source = re.sub(
        r'^(?:async\s+)?def\s+test_\w+[^\n]*\n(?:(?:[ \t][^\n]*|)\n)*',
        '',
        source,
        flags=re.MULTILINE,
    )
    return source.strip()


def call_groq_healer(file_content, error_log, is_production_file: bool = True):
    """Protocolo de Cura Lógica via Groq API."""
    if not GROQ_API_KEY:
        return None

    production_rule = (
        "IMPORTANTE: Este é um arquivo de PRODUÇÃO (não é um arquivo de testes). "
        "NÃO adicione 'import pytest', decoradores '@pytest.mark.*' nem funções 'def test_*()'."
    ) if is_production_file else ""

    prompt = f"""
    SISTEMA: JARVIS AUTO-CURA V3.
    TAREFA: Corrija o erro no código Python baseado no log.
    REGRAS: Retorne APENAS o código completo corrigido. Sem markdown, sem explicações, sem blocos de código delimitados por ```.
    {production_rule}
    
    LOG: {error_log[-2000:]}
    CÓDIGO: {file_content}
    """

    try:
        response = requests.post(GROQ_URL,
                                 headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                                 json={
                                     "model": "llama-3.3-70b-versatile",
                                     "messages": [{"role": "user", "content": prompt}],
                                     "temperature": 0.1
                                 }, timeout=30)
        raw = response.json()['choices'][0]['message']['content'].strip()
        # Always strip markdown fences – LLMs often ignore the instruction
        return _strip_markdown_fences(raw)
    except:
        return None

def mass_reindent(directory_path):
    """Cura estrutural via autopep8."""
    print(f"🧬 Reindentando: {directory_path}")
    subprocess.run([
        "autopep8", "--in-place", "--recursive", "--aggressive",
        "--select=E1,E101,E11,E12", str(directory_path)
    ], check=False)

def heal():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=False)
    parser.add_argument('--log', required=False)
    parser.add_argument('--production-log', required=False,
                        help='Log de erro de produção enviado pelo Field Vision via workflow_dispatch')
    args = parser.parse_args()

    # Exit immediately when there are no failures — avoids unnecessary file
    # changes from mass_reindent that would trigger another workflow run.
    if not _has_failures(args.report):
        print("✅ [Healer] Sem falhas detectadas no relatório. Nenhuma cura necessária.")
        return

    error_context = ""
    target_files = set()

    if args.log and os.path.exists(args.log):
        error_context = Path(args.log).read_text(encoding='utf-8')
        matches = re.findall(r'File "([^"]+\.py)"', error_context)
        target_files.update([Path(f).absolute() for f in matches if ".venv" not in f])

    # Incorpora o log de produção vindo do Field Vision ao contexto de erro
    production_log_path = getattr(args, 'production_log', None)
    if production_log_path and os.path.exists(production_log_path):
        production_log_content = Path(production_log_path).read_text(encoding='utf-8')
        print(f"🧬 [Healer] Log de produção recebido do Field Vision ({len(production_log_content)} chars).")
        error_context = f"=== LOG DE PRODUÇÃO (Field Vision) ===\n{production_log_content}\n\n{error_context}"
        prod_matches = re.findall(r'File "([^"]+\.py)"', production_log_content)
        target_files.update([Path(f).absolute() for f in prod_matches if ".venv" not in f])

    for file_path in target_files:
        if file_path.exists():
            print(f"🩹 Corrigindo lógica: {file_path.name}")
            original = file_path.read_text(encoding='utf-8')
            is_prod = not any(part == "tests" for part in file_path.parts)
            fixed = call_groq_healer(original, error_context, is_production_file=is_prod)
            if fixed and ("def " in fixed or "class " in fixed or "import " in fixed):
                if is_prod:
                    fixed = _strip_injected_test_code(fixed)
                file_path.write_text(fixed, encoding='utf-8')

    target_dirs = ["app/domain/capabilities", "app/core", "scripts"]
    for d in target_dirs:
        dir_path = Path(os.getcwd()) / d
        if dir_path.exists():
            mass_reindent(dir_path)

if __name__ == "__main__":
    heal()
