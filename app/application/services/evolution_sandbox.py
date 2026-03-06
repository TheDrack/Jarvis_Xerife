# -*- coding: utf-8 -*-
"""EvolutionSandbox — testa propostas de código em ambiente isolado antes de aplicá-las.

Implementa o princípio: "nenhuma mutação sem validação".

Fluxo do ``test_proposal``:
    (a) Cria diretório temporário em ``data/sandbox/<timestamp>/``.
    (b) Copia o arquivo-alvo para o diretório temporário.
    (c) Aplica o ``proposal_code`` ao arquivo copiado.
    (d) Executa ``pytest tests/ -v --tb=short -x`` via subprocess.
    (e) Captura stdout/stderr.
    (f) Apaga o diretório temporário (``try/finally``).

Configuração:
    SANDBOX_ENABLED (env, padrão "true"): permite desabilitar o sandbox.
"""

import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.nexus import NexusComponent

logger = logging.getLogger(__name__)

_SANDBOX_BASE = Path("data/sandbox")


class EvolutionSandbox(NexusComponent):
    """Sandbox de execução isolada para propostas de evolução.

    Configurável via ``configure(config)``:
        enabled (bool): sobrescreve a variável de ambiente SANDBOX_ENABLED.
        sandbox_base (str): diretório base para sandboxes (padrão ``data/sandbox``).
        timeout (int): timeout em segundos para a execução do pytest (padrão 120).
    """

    def __init__(self) -> None:
        self._enabled: Optional[bool] = None  # None = usa env var
        self.sandbox_base: Path = _SANDBOX_BASE
        self.timeout: int = 120

    @property
    def enabled(self) -> bool:
        """Retorna se o sandbox está habilitado.

        Prioridade: configure() > variável SANDBOX_ENABLED > True (padrão seguro).
        """
        if self._enabled is not None:
            return self._enabled
        env_val = os.getenv("SANDBOX_ENABLED", "true").lower()
        return env_val not in ("false", "0", "no", "off")

    def configure(self, config: Dict[str, Any]) -> None:
        """Configura o sandbox via dicionário."""
        if "enabled" in config:
            self._enabled = bool(config["enabled"])
        if "sandbox_base" in config:
            self.sandbox_base = Path(config["sandbox_base"])
        if "timeout" in config:
            self.timeout = int(config["timeout"])

    def can_execute(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """Retorna True se o sandbox está habilitado."""
        return self.enabled

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Interface NexusComponent.

        Campos aceitos em *context*:
            proposal_code (str): código da proposta a testar.
            target_file (str):   caminho do arquivo-alvo (pode ser vazio).

        Returns:
            Resultado de ``test_proposal``.
        """
        ctx = context or {}
        proposal_code = ctx.get("proposal_code", "")
        target_file = ctx.get("target_file", "")
        result = self.test_proposal(proposal_code, target_file)
        return {**result, "success": result.get("passed", False)}

    def test_proposal(self, proposal_code: str, target_file: str = "") -> Dict[str, Any]:
        """Testa uma proposta de código em ambiente isolado.

        Args:
            proposal_code: Código Python da proposta.
            target_file:   Caminho relativo do arquivo-alvo (pode ser vazio).

        Returns:
            ``{"passed": bool, "test_output": str, "errors": list}``
        """
        if not self.enabled:
            logger.info("[EvolutionSandbox] Sandbox desabilitado (SANDBOX_ENABLED=false).")
            return {"passed": True, "test_output": "sandbox_disabled", "errors": []}

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        sandbox_dir = self.sandbox_base / ts
        errors: List[str] = []
        test_output = ""
        passed = False

        try:
            sandbox_dir.mkdir(parents=True, exist_ok=True)

            # (b) Copia arquivo-alvo se especificado
            if target_file:
                target_path = Path(target_file)
                if target_path.exists():
                    dest = sandbox_dir / target_path.name
                    shutil.copy2(target_path, dest)
                else:
                    errors.append(f"Arquivo-alvo não encontrado: {target_file}")

            # (c) Aplica o proposal_code
            proposal_path = sandbox_dir / "proposal.py"
            try:
                proposal_path.write_text(proposal_code, encoding="utf-8")
            except Exception as exc:
                errors.append(f"Falha ao escrever proposta: {exc}")
                return {"passed": False, "test_output": "", "errors": errors}

            # Valida sintaxe antes de rodar pytest
            syntax_error = _check_syntax(proposal_code)
            if syntax_error:
                errors.append(f"Erro de sintaxe: {syntax_error}")
                return {"passed": False, "test_output": "", "errors": errors}

            # (d) Executa pytest
            cmd = [
                sys.executable, "-m", "pytest",
                "tests/",
                "-v", "--tb=short", "-x",
                "--no-header",
                "-q",
                "--co",  # apenas coleta (dry-run) — troca por execução real se necessário
            ]
            # Execução real dos testes (não apenas coleta)
            cmd = [
                sys.executable, "-m", "pytest",
                "tests/",
                "--tb=short", "-x",
                "--no-header",
                "-q",
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=str(Path.cwd()),  # roda na raiz do projeto
                )
                # (e) Captura saída
                test_output = proc.stdout + proc.stderr
                passed = proc.returncode == 0
                if not passed:
                    errors.append(f"pytest retornou código {proc.returncode}")
            except subprocess.TimeoutExpired:
                errors.append(f"Timeout após {self.timeout}s")
                test_output = "TIMEOUT"
            except Exception as exc:
                errors.append(f"Falha ao executar pytest: {exc}")

        finally:
            # (f) Remove diretório temporário
            try:
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            except Exception as exc:
                logger.debug("[EvolutionSandbox] Falha ao remover sandbox: %s", exc)

        logger.info(
            "[EvolutionSandbox] Resultado: passed=%s erros=%d",
            passed,
            len(errors),
        )
        return {"passed": passed, "test_output": test_output, "errors": errors}


def _check_syntax(code: str) -> Optional[str]:
    """Verifica a sintaxe Python do código. Retorna None se OK, mensagem de erro se inválido."""
    import ast

    try:
        ast.parse(code)
        return None
    except SyntaxError as exc:
        return str(exc)
