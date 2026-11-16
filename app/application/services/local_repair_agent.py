# -*- coding: utf-8 -*-
"""
LocalRepairAgent — Primeiro estágio do pipeline de Self-Healing.
Reduz latência de reparo de ~90s (CI) para milissegundos nos casos cobertos.
"""
import ast
import importlib
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from app.core.nexus import NexusComponent, nexus
from app.application.security.repository_path_policy import (
    UnsafeRepositoryPath,
    contains_frozen_directory,
    is_test_or_pytest_infrastructure_path,
    protected_prefix_for,
    resolve_repository_path,
)

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]

SAFE_AUTO_INSTALL: frozenset = frozenset(
    {"instructor", "json_repair", "json-repair", "httpx", "pydantic", "faiss", "litellm"}
)
_MAX_FILE_CONTENT_LENGTH = 4000
_MAX_TRACEBACK_LENGTH = 1200


class LocalRepairAgent(NexusComponent):

    def execute(self, context: dict) -> dict:
        """
        Context: error_type, error_message, traceback, file_path (opcional)
        Retorna: success, fixed, method ("deterministic"|"local_llm"|"none"), escalate_to_ci, details
        """
        error_type = context.get("error_type", "")
        error_message = context.get("error_message", "")
        traceback_text = context.get("traceback", "")
        file_path = context.get("file_path")

        # Estágio 1: determinístico
        result = self._try_deterministic(error_type, error_message, file_path)
        if result.get("fixed"):
            return {**result, "success": True, "method": "deterministic", "escalate_to_ci": False}

        # Estágio 2: LLM local
        result = self._try_llm(error_type, error_message, traceback_text, file_path)
        if result.get("fixed"):
            return {**result, "success": True, "method": "local_llm", "escalate_to_ci": False}

        return {
            "success": False,
            "fixed": False,
            "method": "none",
            "escalate_to_ci": True,
            "details": f"Sem reparo local para {error_type}",
        }

    def _try_deterministic(
        self, error_type: str, error_message: str, file_path: Optional[str]
    ) -> dict:
        if error_type in ("ModuleNotFoundError", "ImportError"):
            return self._install_missing(error_message)
        if error_type == "SyntaxError" and file_path:
            target, rejection = self._resolve_patch_target(file_path, None)
            if target is None:
                return {"fixed": False, "details": rejection}
            try:
                ast.parse(target.read_text(encoding="utf-8"))
                return {"fixed": False}
            except SyntaxError as exc:
                return {
                    "fixed": False,
                    "details": f"SyntaxError em {target}:{exc.lineno} — requer LLM",
                }
            except OSError as exc:
                return {
                    "fixed": False,
                    "details": f"Não foi possível ler o arquivo autorizado: {type(exc).__name__}",
                }
        return {"fixed": False}

    def _install_missing(self, error_message: str) -> dict:
        match = re.search(r"No module named '([^']+)'", error_message)
        if not match:
            return {"fixed": False}
        module = match.group(1).split(".")[0]
        package = module.replace("_", "-")
        if module not in SAFE_AUTO_INSTALL and package not in SAFE_AUTO_INSTALL:
            return {"fixed": False, "details": f"'{module}' fora da whitelist de auto-install"}
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package, "-q"],
                check=True,
                timeout=60,
                capture_output=True,
            )
            importlib.import_module(module)
            return {"fixed": True, "details": f"Instalado: {package}"}
        except Exception as exc:
            return {"fixed": False, "details": f"Falha ao instalar {package}: {exc}"}

    def _try_llm(
        self,
        error_type: str,
        error_message: str,
        traceback_text: str,
        file_path: Optional[str],
    ) -> dict:
        # Validate the source path before reading any file content or sending a
        # prompt to a provider. Error logs and caller-supplied paths are untrusted.
        target, rejection = self._resolve_patch_target(file_path, None)
        if target is None:
            return {"fixed": False, "details": rejection}
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            return {
                "fixed": False,
                "details": f"Não foi possível ler o arquivo autorizado: {type(exc).__name__}",
            }
        file_content = text[:_MAX_FILE_CONTENT_LENGTH] + (
            "\n...[truncado]" if len(text) > _MAX_FILE_CONTENT_LENGTH else ""
        )

        prompt = f"""Analise o erro e gere um patch de correção Python.

ERRO: {error_type}: {error_message}
TRACEBACK:
{traceback_text[:_MAX_TRACEBACK_LENGTH]}
ARQUIVO AUTORIZADO: {file_path or 'nenhum'}
Use somente o arquivo autorizado acima. Não escolha nem redirecione para outro caminho.
Se não houver arquivo autorizado, responda can_fix=false.
CONTEÚDO:
{file_content}

Responda com este JSON exato (sem markdown):
{{
  "can_fix": true/false,
  "confidence": 0.0-1.0,
  "explanation": "o que está errado",
  "file_path": "caminho do arquivo",
  "old_code": "trecho exato a substituir ou null",
  "new_code": "trecho corrigido ou null",
  "action": "replace|install_package",
  "package_name": "nome do pacote ou null"
}}"""

        # Tenta primeiro via llm_engine com marcha REPARO (sistema interno de marchas)
        result = self._call_via_llm_engine(prompt)
        if result.get("success"):
            try:
                patch = json.loads(result["response"])
                return self._apply_patch(patch, file_path)
            except Exception as exc:
                return {"fixed": False, "details": f"Falha ao parsear patch: {exc}"}

        # Fallback: OllamaAdapter direto (suporta json_mode e system prompt)
        try:
            ollama = nexus.resolve("ollama_adapter")
        except Exception:
            return {"fixed": False, "details": "OllamaAdapter não registrado no Nexus"}

        if not ollama or (hasattr(ollama, "is_available") and not ollama.is_available()):
            return {"fixed": False, "details": "Ollama não acessível em localhost:11434"}

        result = ollama.execute(
            {
                "prompt": prompt,
                "json_mode": True,
                "system": "Agente de reparo Python. Responda APENAS com JSON válido, sem markdown.",
            }
        )
        if not result.get("success"):
            return {"fixed": False, "details": f"Ollama falhou: {result.get('error')}"}

        try:
            patch = json.loads(result["response"])
            return self._apply_patch(patch, file_path)
        except Exception as exc:
            return {"fixed": False, "details": f"Falha ao parsear patch: {exc}"}

    def _call_via_llm_engine(self, prompt: str) -> dict:
        """Chama o LLM Engine com marcha REPARO (ollama/llama3) via sistema interno de marchas."""
        try:
            llm_engine = nexus.resolve("llm_engine")
            if not llm_engine:
                return {"success": False}
            context = {
                "metadata": {"marcha": "REPARO", "user_input": prompt},
                "artifacts": {},
            }
            result_ctx = llm_engine.execute(context)
            response = result_ctx.get("artifacts", {}).get("llm_response", "")
            if response:
                return {"success": True, "response": response}
        except Exception:
            pass
        return {"success": False}

    def _resolve_patch_target(
        self, original_path: Optional[str], proposed_path: Optional[str]
    ) -> tuple[Optional[Path], str]:
        """Resolve a single trusted source file; the model cannot choose a new target."""
        if not original_path:
            return None, "Nenhum arquivo de origem confiável foi fornecido."

        root = Path(REPO_ROOT).resolve()

        def relative_path(raw_path: str) -> str:
            candidate = Path(raw_path)
            if candidate.is_absolute():
                try:
                    return candidate.relative_to(root).as_posix()
                except ValueError as exc:
                    raise UnsafeRepositoryPath(
                        "o caminho absoluto está fora do repositório"
                    ) from exc
            return candidate.as_posix()

        try:
            target, normalized_relative, target_relative = resolve_repository_path(
                root, relative_path(original_path), reject_symlinks=True
            )
            if not target.is_file():
                return None, "O arquivo de origem confiável não existe."
            if contains_frozen_directory(normalized_relative) or contains_frozen_directory(target_relative):
                return None, "Arquivos .frozen são imutáveis para auto-reparo."
            if target.suffix.casefold() != ".py":
                return None, "O reparo local só pode alterar arquivos Python."
            protected = protected_prefix_for(target_relative)
            if protected:
                return None, f"O caminho pertence à área protegida: {protected}."
            if is_test_or_pytest_infrastructure_path(target_relative):
                return None, "Testes e configuração pytest são imutáveis para auto-reparo."

            if proposed_path:
                proposed, _, _ = resolve_repository_path(
                    root, relative_path(proposed_path), reject_symlinks=True
                )
                if proposed != target:
                    return None, "O modelo tentou redirecionar o patch para outro arquivo."

            return target, ""
        except (UnsafeRepositoryPath, OSError, RuntimeError, ValueError, TypeError) as exc:
            return None, f"Caminho de reparo rejeitado: {exc}"

    def _apply_patch(self, patch: dict, original_path: Optional[str]) -> dict:
        if not patch.get("can_fix"):
            return {"fixed": False, "details": patch.get("explanation", "")}

        confidence = float(patch.get("confidence", 0))
        if confidence < 0.6:
            return {"fixed": False, "details": f"Confiança insuficiente ({confidence:.0%})"}

        action = patch.get("action")

        if action == "install_package":
            return self._install_missing(f"No module named '{patch.get('package_name', '')}'")

        if action == "replace":
            old_code, new_code = patch.get("old_code"), patch.get("new_code")
            if not all([old_code, new_code]):
                return {
                    "fixed": False,
                    "details": "Patch incompleto: old_code/new_code ausente",
                }
            path, rejection = self._resolve_patch_target(
                original_path, patch.get("file_path")
            )
            if path is None:
                return {"fixed": False, "details": rejection}

            content = path.read_text(encoding="utf-8")
            if old_code not in content:
                return {
                    "fixed": False,
                    "details": "old_code não encontrado no arquivo — patch desatualizado",
                }
            try:
                ast.parse(new_code)  # valida sintaxe antes de aplicar
            except SyntaxError as exc:
                return {"fixed": False, "details": f"new_code com SyntaxError: {exc}"}
            path.write_text(content.replace(old_code, new_code, 1), encoding="utf-8")
            logger.info(
                "Patch aplicado em %s (confiança %.0f%%)", path, confidence * 100
            )
            return {
                "fixed": True,
                "details": patch.get("explanation", "Patch aplicado"),
                "confidence": confidence,
            }

        return {"fixed": False, "details": f"action '{action}' não suportada"}
