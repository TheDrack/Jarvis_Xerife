# -*- coding: utf-8 -*-
"""JARVIS Healer — Auto-cura baseada em logs de erro.
CORREÇÃO CRÍTICA: Padrões regex escapados para evitar markdown injection.
"""
import json
import logging
import os
import re
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Healer")

# ============================================================================
# CONFIGURAÇÕES E PADRÕES
# ============================================================================

REPO_ROOT = Path(__file__).resolve().parent.parent

ERROR_PATTERNS = [
    (r"ModuleNotFoundError: No module named '(\w+)'", "ModuleNotFoundError"),
    (r"ImportError: cannot import name '(\w+)'", "ImportError"),
    (r"SyntaxError: invalid syntax", "SyntaxError"),
    (r"IndentationError: unexpected indent", "IndentationError"),
    (r"NameError: name '(\w+)' is not defined", "NameError"),
    (r"AttributeError: '(\w+)' object has no attribute", "AttributeError"),
    (r"TypeError: '(\w+)' object is not callable", "TypeError"),
]

# CORREÇÃO: Flags compiladas separadamente para evitar confusão do parser
MULTILINE_FLAG = re.MULTILINE
IGNORECASE_FLAG = re.IGNORECASE


# ============================================================================
# FUNÇÕES DE UTILIDADE E PARSING
# ============================================================================

def extract_files_from_log(log_content: str) -> List[Path]:
    """Extrai caminhos de arquivos .py existentes no log de erro."""
    matches = re.findall(r'File "([^"]+\.py)"', log_content)
    found_files = []    
    for f in matches:
        p = Path(f).absolute()
        if p.exists() and ".venv" not in str(p) and "lib/python" not in str(p):
            found_files.append(p)
    return list(set(found_files))


def is_production_file(file_path: Path) -> bool:
    """Verifica se o arquivo pertence à lógica de produção."""
    path_str = str(file_path).lower()
    return "tests/" not in path_str and "test_" not in file_path.name.lower()


def _strip_markdown_fences(text: str) -> str:
    """
    Remove blocos de código markdown.
    CORREÇÃO: Usa abordagem character-by-character para evitar regex injection.
    """
    if not text:
        return ""
    
    # CORREÇÃO: Abordagem segura sem regex complexo
    lines = text.split('\n')
    cleaned_lines = []
    in_code_block = False
    
    for line in lines:
        # Detecta início/fim de bloco de código de forma segura
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        
        if not in_code_block:
            cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines)
    
    # Remove linguagem do bloco se existir (ex: ```python)
    if result.startswith('python\n'):
        result = result[8:]
    
    return result.strip()


def _strip_injected_test_code(source: str) -> str:
    """Remove código de teste injetado acidentalmente."""
    # CORREÇÃO: Padrões simplificados para evitar confusão do parser
    patterns_to_remove = [
        r'(?:^|\n)[ \t]*(?:import pytest|from pytest)[^\n]*',        r'^[ \t]*@pytest\.[^\n]+\n',
        r'^(?:async\s+)?def\s+test_\w+[^\n]*(?:\n(?:[ \t]+[^\n]*|))*',
    ]
    
    for pattern in patterns_to_remove:
        source = re.sub(pattern, '', source, flags=MULTILINE_FLAG)
    
    return source.strip()


# ============================================================================
# FUNÇÕES DE HEALING
# ============================================================================

def _call_metabolism_core(file_content: str, error_log: str, is_production_file: bool) -> Optional[str]:
    """Chama MetabolismCore (frota multi-LLM) para obter o código corrigido."""
    try:
        from app.core.nexus import nexus
    except ImportError:
        return None
    
    try:
        core = nexus.resolve("metabolism_core")
        
        if core is None or getattr(core, "__is_cloud_mock__", False):
            return None
        
        prompt = _build_healer_prompt(file_content, error_log, is_production_file)
        raw = core.ask_jarvis(
            "Você é o sistema JARVIS AUTO-CURA. Corrija código Python retornando apenas o código corrigido.",
            prompt,
            require_json=False,
        )
        
        if raw and isinstance(raw, str):
            return _strip_markdown_fences(raw)
    
    except Exception as exc:
        logger.debug(f"[Healer] MetabolismCore falhou: {exc}")
        return None
    
    return None


def _call_groq_direct(file_content: str, error_log: str, is_production_file: bool) -> Optional[str]:
    """Fallback direto para Groq API."""
    try:
        import httpx
        
        api_key = os.getenv("GROQ_API_KEY")        if not api_key:
            logger.warning("[Healer] GROQ_API_KEY não configurada")
            return None
        
        prompt = _build_healer_prompt(file_content, error_log, is_production_file)
        
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            timeout=30.0,
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            return _strip_markdown_fences(content)
    
    except Exception as exc:
        logger.debug(f"[Healer] Groq direto falhou: {exc}")
    
    return None


def call_groq_healer(file_content: str, error_log: str, is_production_file: bool = True) -> Optional[str]:
    """Protocolo de Cura — MetabolismCore com fallback Groq."""
    # Tenta MetabolismCore primeiro
    result = _call_metabolism_core(file_content, error_log, is_production_file)
    if result:
        logger.info("[Healer] MetabolismCore retornou correção")
        return result
    
    # Fallback: Groq direto
    logger.info("[Healer] Fallback para Groq direto")
    return _call_groq_direct(file_content, error_log, is_production_file)


def _build_healer_prompt(file_content: str, error_log: str, is_production_file: bool) -> str:
    """
    Constrói prompt para o healer.
    CORREÇÃO: Strings formatadas de forma segura.
    """    production_rule = (
        "IMPORTANTE: Este é um arquivo de PRODUÇÃO (não é um arquivo de testes). "
        "NÃO adicione 'import pytest', decoradores '@pytest.mark.*' nem funções 'def test_*()'."
    ) if is_production_file else ""
    
    # CORREÇÃO: Usar concatenação explícita para evitar confusão do parser
    prompt_parts = [
        "SISTEMA: JARVIS AUTO-CURA V3.",
        "TAREFA: Corrija o erro no código Python baseado no log.",
        "REGRAS: Retorne APENAS o código completo corrigido.",
        "Sem markdown, sem explicações, sem blocos de código delimitados.",
        production_rule,
        "LOG:",
        error_log[-2000:],
        "CÓDIGO:",
        file_content
    ]
    
    return "\n".join(prompt_parts)


def apply_fixes(file_path: Path, fixes: List[Dict[str, Any]], dry_run: bool = False) -> tuple:
    """Aplica correções ao arquivo."""
    success = 0
    fail = 0
    
    try:
        original = file_path.read_text(encoding="utf-8")
        
        for fix in fixes:
            if fix.get("action") == "replace":
                old_code = fix.get("old_code", "")
                new_code = fix.get("new_code", "")
                
                if old_code in original:
                    if not dry_run:
                        original = original.replace(old_code, new_code)
                    success += 1
                else:
                    fail += 1
        
        if not dry_run and success > 0:
            file_path.write_text(original, encoding="utf-8")
            logger.info(f"✅ {file_path}: {success} correções aplicadas")
    
    except Exception as e:
        logger.error(f"❌ Erro ao aplicar fix em {file_path}: {e}")
        fail += 1
    
    return success, fail

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def heal():
    """Função principal do healer."""
    parser = argparse.ArgumentParser(description="JARVIS Healer")
    parser.add_argument("--report", required=True, help="Path para pytest JSON report")
    parser.add_argument("--log", required=True, help="Path para pytest log")
    parser.add_argument("--production-log", help="Path para log de produção")
    parser.add_argument("--workflow-log", help="Path para log de workflow CI")
    parser.add_argument("--dry-run", action="store_true", help="Não aplica correções")
    
    args = parser.parse_args()
    
    # Carrega report de erros
    error_context = ""
    target_files = set()
    
    # Lê pytest log
    pytest_log_path = Path(args.log)
    if pytest_log_path.exists():
        pytest_log_content = pytest_log_path.read_text(encoding="utf-8")
        error_context += f"=== PYTEST LOG ===\n{pytest_log_content}\n"
        
        # Extrai arquivos com erro
        prod_matches = re.findall(r'File "([^"]+\.py)"', pytest_log_content)
        target_files.update([Path(f).absolute() for f in prod_matches if ".venv" not in f])
    
    # Lê production log se disponível
    production_log_path = getattr(args, 'production_log', None)
    if production_log_path and os.path.exists(production_log_path):
        production_log_content = Path(production_log_path).read_text(encoding="utf-8")
        error_context += f"=== PRODUCTION LOG ===\n{production_log_content}\n"
        
        prod_matches = re.findall(r'File "([^"]+\.py)"', production_log_content)
        target_files.update([Path(f).absolute() for f in prod_matches if ".venv" not in f])
    
    # Lê workflow log se disponível
    workflow_log_path = getattr(args, 'workflow_log', None)
    if workflow_log_path and os.path.exists(workflow_log_path):
        workflow_log_content = Path(workflow_log_path).read_text(encoding="utf-8")
        logger.info(f"🔍 [Healer] Log do workflow CI recebido ({len(workflow_log_content)} chars).")
        error_context += f"=== WORKFLOW CI LOG ===\n{workflow_log_content}\n"
    
    if not target_files:
        logger.warning("⚠️ [Healer] Nenhum arquivo alvo identificado")
        return 1    
    logger.info(f"🩹 Arquivos para correção: {len(target_files)}")
    
    total_success = 0
    total_fail = 0
    
    for file_path in target_files:
        if not file_path.exists():
            logger.warning(f"⚠️ Arquivo não encontrado: {file_path}")
            continue
        
        is_prod = is_production_file(file_path)
        original = file_path.read_text(encoding="utf-8")
        
        logger.info(f"🩹 Corrigindo lógica: {file_path.name}")
        
        fixed = call_groq_healer(original, error_context, is_production_file=is_prod)
        
        if fixed and fixed != original:
            try:
                compile(fixed, str(file_path), "exec")
                if not args.dry_run:
                    file_path.write_text(fixed, encoding="utf-8")
                logger.info(f"✅ {file_path.name}: correção aplicada")
                total_success += 1
            except SyntaxError as e:
                logger.error(f"❌ {file_path.name}: correção rejeitada (SyntaxError: {e})")
                total_fail += 1
        else:
            logger.warning(f"⚠️ {file_path.name}: nenhuma correção gerada")
            total_fail += 1
    
    logger.info(f"\n📊 Resultado: {total_success} sucesso, {total_fail} falha")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(heal())