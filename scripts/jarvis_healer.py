# -*- coding: utf-8 -*-
"""JARVIS Healer — Auto-cura baseada em logs de erro.
CORREÇÃO: Fallback para Groq direto se Nexus falhar.
"""
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("Healer")

# ============================================================================
# CONFIGURAÇÕES
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

# ============================================================================
# FUNÇÕES DE HEALING
# ============================================================================

def extract_file_from_error(error_log: str) -> Optional[Path]:
    """Extrai caminho do arquivo do log de erro."""
    match = re.search(r'File "([^"]+\.py)"', error_log)
    if match:
        return Path(match.group(1))
    return None


def classify_error_type(error_log: str) -> str:
    """Classifica o tipo de erro."""
    for pattern, error_type in ERROR_PATTERNS:
        if re.search(pattern, error_log):
            return error_type    return "UnknownError"


def is_production_file(file_path: Path) -> bool:
    """Verifica se arquivo é de produção (não teste)."""
    return "tests/" not in str(file_path) and "test_" not in file_path.name


def strip_test_code(source: str) -> str:
    """Remove código de teste do source."""
    source = re.sub(r'(?:^|\n)[ \t]*(?:import pytest|from pytest)[^\n]*', '', source, flags=re.MULTILINE)
    source = re.sub(r'^[ \t]*@pytest\.[^\n]+\n', '', source, flags=re.MULTILINE)
    source = re.sub(r'^(?:async\s+)?def\s+test_\w+[^\n]*(?:\n(?:[ \t]+[^\n]*|))*', '', source, flags=re.MULTILINE)
    return source.strip()


def _call_metabolism_core(file_content: str, error_log: str, is_production_file: bool) -> Optional[str]:
    """Tenta usar MetabolismCore (pode falhar se Nexus estiver quebrado)."""
    try:
        from app.core.nexus import nexus
        core = nexus.resolve("metabolism_core")
        
        if core is None or getattr(core, "__is_cloud_mock__", False):
            logger.debug("[Healer] MetabolismCore indisponível")
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
        
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:            logger.warning("[Healer] GROQ_API_KEY não configurada")
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
    """Constrói prompt para o healer."""
    production_rule = (
        "IMPORTANTE: Este é um arquivo de PRODUÇÃO (não é teste). "
        "NÃO adicione 'import pytest', decoradores '@pytest.mark.*' nem funções 'def test_*()'."
    ) if is_production_file else ""    
    return (
        "SISTEMA: JARVIS AUTO-CURA V3.\n"
        "TAREFA: Corrija o erro no código Python baseado no log.\n"
        "REGRAS: Retorne APENAS o código completo corrigido. "
        "Sem markdown, sem explicações, sem blocos de código delimitados por ```.\n"
        f"{production_rule}\n"
        f"LOG:\n{error_log[-2000:]}\n"
        f"CÓDIGO:\n{file_content}"
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove fences de markdown do texto."""
    if not text:
        return ""
    text = re.sub(r'^```(?:python)?\n', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n```$', '', text, flags=re.MULTILINE)
    return text.strip()


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
    import argparse
    
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
        workflow_log_content = Path(workflow_log_path).read_text(encoding="utf-8')
        logger.info(f"🔍 [Healer] Log do workflow CI recebido ({len(workflow_log_content)} chars).")
        error_context += f"=== WORKFLOW CI LOG ===\n{workflow_log_content}\n"
    
    if not target_files:        logger.warning("⚠️ [Healer] Nenhum arquivo alvo identificado")
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