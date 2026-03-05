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

logger = logging.getLogger(__name__)

SAFE_AUTO_INSTALL = {"instructor", "json_repair", "json-repair", "httpx", "pydantic", "faiss"}
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
            try:
                ast.parse(Path(file_path).read_text(encoding="utf-8"))
                return {"fixed": False}
            except SyntaxError as exc:
                return {
                    "fixed": False,
                    "details": f"SyntaxError em {file_path}:{exc.lineno} — requer LLM",
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
        file_content = ""
        if file_path and Path(file_path).exists():
            try:
                text = Path(file_path).read_text(encoding="utf-8")
                file_content = text[:_MAX_FILE_CONTENT_LENGTH] + (
                    "\n...[truncado]" if len(text) > _MAX_FILE_CONTENT_LENGTH else ""
                )
            except Exception:
                pass

        prompt = f"""Analise o erro e gere um patch de correção Python.

ERRO: {error_type}: {error_message}
TRACEBACK:
{traceback_text[:_MAX_TRACEBACK_LENGTH]}
ARQUIVO: {file_path or 'desconhecido'}
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
            file_path = patch.get("file_path") or original_path
            old_code, new_code = patch.get("old_code"), patch.get("new_code")
            if not all([file_path, old_code, new_code]):
                return {
                    "fixed": False,
                    "details": "Patch incompleto: file_path/old_code/new_code ausente",
                }
            path = Path(file_path)
            if not path.exists():
                return {"fixed": False, "details": f"Arquivo não encontrado: {file_path}"}
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
                "Patch aplicado em %s (confiança %.0f%%)", file_path, confidence * 100
            )
            return {
                "fixed": True,
                "details": patch.get("explanation", "Patch aplicado"),
                "confidence": confidence,
            }

        return {"fixed": False, "details": f"action '{action}' não suportada"}
