from app.core.nexus import NexusComponent
# -*- coding: utf-8 -*-
"""Auto-repair mixin for the Gateway LLM adapter.

Provides the self-healing logic that analyses runtime errors with Gemini and
dispatches automated fixes through GitHub Actions.  Designed to be mixed into
GatewayLLMCommandAdapter.
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class AutoRepairMixin(NexusComponent):
    """Mixin that adds AI-powered auto-repair capabilities to an LLM adapter.

    Host class must expose the following attributes / methods:
        - self.github_adapter  – GitHubAdapter instance (or None)
        - self.gemini_adapter  – LLMCommandAdapter instance (or None)
        - self.gateway         – AIGateway instance
        - self.RECOMMENDED_GEMINI_MODEL  – str
        - self._extract_response_text(result) -> Optional[str]
        - self._log_error_locally(message) -> None
    """

    def execute(self, context: dict):
        logger.debug("[NEXUS] %s.execute() aguardando implementação.", self.__class__.__name__)
        return {"success": False, "not_implemented": True}

    async def _attempt_auto_repair(self, error_traceback: str, user_input: str) -> None:
        """Attempt to auto-repair the error by sending it to Gemini for analysis.

        This method sends the error traceback to Gemini with instructions to:
        1. Analyze the error
        2. Identify the file causing the error
        3. Generate a JSON with file_path, original_code, and fix_code

        Args:
            error_traceback: Full error traceback from traceback.format_exc()
            user_input: The user input that caused the error
        """
        if not self.github_adapter:
            logger.info("GitHub adapter not available, skipping auto-repair")
            return

        if not self.gemini_adapter:
            logger.warning("Gemini adapter not available for auto-repair analysis")
            return

        try:
            logger.info("🔧 Attempting auto-repair via Gemini analysis...")

            instruction = f"""Analise este erro de sistema, identifique o arquivo causador e gere um JSON com: file_path, original_code e fix_code.

ERRO DO SISTEMA:
{error_traceback}

INPUT DO USUÁRIO:
{user_input}

INSTRUÇÕES:
1. Analise o traceback completo para identificar o arquivo causador do erro
2. Identifique o código original que está causando o erro
3. Gere uma correção apropriada para o código
4. Retorne APENAS um JSON válido no seguinte formato (sem markdown, sem texto adicional):
{{
  "file_path": "caminho/completo/do/arquivo.py",
  "original_code": "código original com erro",
  "fix_code": "código corrigido"
}}

IMPORTANTE: Retorne APENAS o JSON, sem texto antes ou depois."""

            messages = [{"role": "user", "content": instruction}]

            result = await self.gateway.generate_completion(
                messages=messages,
                functions=None,
                multimodal=False,
            )

            response_text = self._extract_response_text(result)

            if not response_text:
                logger.warning("No response from Gemini for auto-repair analysis")
                return

            logger.info(f"Gemini auto-repair analysis received: {response_text[:200]}...")

            try:
                json_text = response_text.strip()
                if json_text.startswith("```"):
                    json_text = json_text.split("```")[1]
                    if json_text.startswith("json"):
                        json_text = json_text[4:]
                    json_text = json_text.strip()

                repair_data = json.loads(json_text)

                required_fields = ["file_path", "original_code", "fix_code"]
                if not all(field in repair_data for field in required_fields):
                    logger.error(
                        f"Invalid JSON response from Gemini: missing fields. "
                        f"Got: {repair_data.keys()}"
                    )
                    return

                issue_data = {
                    "issue_title": f"Auto-fix: Error in {repair_data['file_path']}",
                    "file_path": repair_data["file_path"],
                    "fix_code": repair_data["fix_code"],
                    "test_command": "pytest -W ignore::DeprecationWarning tests/",
                }

                logger.info(f"Dispatching auto-fix to GitHub for {repair_data['file_path']}")
                result = await self.github_adapter.dispatch_auto_fix(issue_data)

                if result.get("success"):
                    logger.info(
                        f"✅ Auto-fix dispatched successfully: {result.get('workflow_url')}"
                    )
                else:
                    error_msg = f"Failed to dispatch auto-fix to GitHub: {result.get('error')}"
                    logger.error(error_msg)
                    self._log_error_locally(error_msg)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from Gemini response: {e}")
                logger.error(f"Response was: {response_text}")
                self._log_error_locally(f"JSON parse error: {e}\nResponse: {response_text}")

        except Exception as e:
            error_msg = f"Error in auto-repair attempt: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._log_error_locally(error_msg)

    async def _handle_critical_error(self, error: Exception, user_input: str) -> None:
        """Handle critical errors by triggering self-healing mechanism.

        Detects specific critical errors (model decommissioned, test failures, etc.)
        and triggers the auto-fix workflow via GitHub Actions.

        Args:
            error: The exception that occurred
            user_input: The user input that caused the error
        """
        if not self.github_adapter:
            logger.info("GitHub adapter not available, skipping self-healing")
            return

        error_str = str(error).lower()
        error_type = type(error).__name__

        is_critical = any([
            "model_decommissioned" in error_str,
            "model has been decommissioned" in error_str,
            "model not found" in error_str,
            "test fail" in error_str,
            "quota" in error_str and "exceeded" in error_str,
            "rate limit" in error_str and "groq" not in error_str,
            "authentication failed" in error_str,
            "api key" in error_str and "invalid" in error_str,
        ])

        if not is_critical:
            logger.debug(f"Error is not critical, skipping self-healing: {error_type}")
            return

        logger.warning(f"🔧 Critical error detected: {error_type} - {error}")

        try:
            fix_plan = await self._formulate_correction_plan(error, user_input)

            if fix_plan:
                logger.info(f"Dispatching auto-fix for critical error: {error_type}")
                result = await self.github_adapter.dispatch_auto_fix(fix_plan)

                if result.get("success"):
                    logger.info(
                        f"✅ Auto-fix dispatched successfully: {result.get('workflow_url')}"
                    )
                else:
                    logger.error(f"❌ Failed to dispatch auto-fix: {result.get('error')}")
            else:
                logger.warning("Could not formulate a correction plan")

        except Exception as heal_error:
            logger.error(f"Error in self-healing process: {heal_error}", exc_info=True)

    async def _formulate_correction_plan(
        self,
        error: Exception,
        user_input: str,
    ) -> Optional[dict]:
        """Use Gemini to formulate a correction plan for the detected error.

        Args:
            error: The exception that occurred
            user_input: The user input that caused the error

        Returns:
            Dictionary with fix plan (issue_title, file_path, fix_code, test_command)
            or None if unable to formulate a plan
        """
        if not self.gemini_adapter:
            logger.warning("Gemini adapter not available for correction planning")
            return None

        try:
            error_type = type(error).__name__
            error_msg = str(error)

            diagnostic_prompt = f"""
ERRO CRÍTICO DETECTADO EM PRODUÇÃO

Tipo de Erro: {error_type}
Mensagem: {error_msg}
Input do Usuário: {user_input}

Contexto: O Jarvis está rodando no Render e detectou este erro crítico.

TAREFA: Analise o erro e determine se é possível formular uma correção automática.

Para erros relacionados a:
1. Model decommissioned/deprecated: Sugerir atualização do modelo
2. API key invalid: Indicar necessidade de configuração manual
3. Rate limits permanentes: Sugerir mudança de provider
4. Test failures: Analisar causa e propor correção

Responda em formato estruturado:
- É possível auto-correção? (sim/não)
- Arquivo afetado: (caminho completo do arquivo)
- Título da issue: (descrição breve)
- Comando de teste: (comando pytest específico ou vazio)
- Descrição técnica: (explicação do problema e solução)

Se não for possível auto-correção, explique o motivo.
"""

            messages = [{"role": "user", "content": diagnostic_prompt}]

            result = await self.gateway.generate_completion(
                messages=messages,
                functions=None,
                multimodal=False,
            )

            response_text = self._extract_response_text(result)

            if not response_text:
                logger.warning("No response from Gemini for correction planning")
                return None

            logger.info(f"Gemini analysis: {response_text}")

            if "não" in response_text.lower() and "possível" in response_text.lower():
                logger.info("Gemini determined auto-fix is not possible")
                return None

            fix_plan = self._parse_fix_plan_from_response(response_text, error)

            return fix_plan

        except Exception as e:
            logger.error(f"Error formulating correction plan: {e}", exc_info=True)
            return None

    def _parse_fix_plan_from_response(
        self,
        response: str,
        error: Exception,
    ) -> Optional[dict]:
        """Parse Gemini's response to extract fix plan details.

        Args:
            response: Gemini's text response
            error: The original error

        Returns:
            Dictionary with fix plan or None
        """
        error_str = str(error).lower()

        plan = {
            "issue_title": f"Auto-fix: {type(error).__name__}",
            "file_path": "",
            "fix_code": "",
            "test_command": "pytest -W ignore::DeprecationWarning tests/",
        }

        if "model_decommissioned" in error_str or "model has been decommissioned" in error_str:
            plan["issue_title"] = "Fix model_decommissioned error"
            plan["file_path"] = "app/adapters/infrastructure/gemini_adapter.py"

            file_path = os.path.join(os.getcwd(), plan["file_path"])
            try:
                with open(file_path, "r") as f:
                    current_code = f.read()

                import re

                new_model = self.RECOMMENDED_GEMINI_MODEL
                fixed_code = re.sub(
                    r'\bmodel_name:\s*str\s*=\s*"gemini-flash-latest"',
                    f'model_name: str = "{new_model}"',
                    current_code,
                )
                fixed_code = re.sub(
                    r'\bgemini_model:\s*str\s*=\s*"gemini-flash-latest"',
                    f'gemini_model: str = "{new_model}"',
                    fixed_code,
                )

                plan["fix_code"] = fixed_code
                plan["test_command"] = "pytest tests/adapters/ -k gemini -v"

                return plan
            except Exception as e:
                logger.error(f"Error reading file for fix: {e}")
                return None

        logger.info("Error type not yet supported for automatic fixing")
        return None
