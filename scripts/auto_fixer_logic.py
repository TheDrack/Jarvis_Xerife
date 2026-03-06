#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Auto-Fixer Logic Script - GitHub Copilot Native Integration

Main orchestration entry point for the Jarvis self-healing system.
Delegates parsing to issue_parser, fix generation to fix_applier, and
Git/PR operations to pr_manager.

Usage:
    export ISSUE_BODY="Error: ..." && export ISSUE_ID="123"
    python scripts/auto_fixer_logic.py [--state path/to/pytest-report.json]
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Add the project root to sys.path so app.* imports work in sub-modules
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_ROOT))

from app.utils.document_store import document_store

# Import sub-modules (must come after sys.path insertion)
from scripts import fix_applier, pr_manager
from scripts.state_machine import ErrorCategory, FailureReason, SelfHealingStateMachine, State

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Maximum number of auto-healing attempts to prevent infinite loops
MAX_HEALING_ATTEMPTS = 3


class AutoFixerError(Exception):
    """Base exception for auto-fixer errors."""


class AutoFixer:
    """Auto-Fixer orchestrator for the Jarvis self-healing system."""

    def __init__(self, repo_path: Optional[str] = None):
        """Initialise the auto-fixer; validates gh CLI and Copilot extension."""
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._check_gh_cli()
        self._check_gh_copilot_extension()

    def _check_gh_cli(self) -> bool:
        """Check if GitHub CLI is installed and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("✓ GitHub CLI is authenticated")
                return True
            logger.warning("⚠ GitHub CLI is not authenticated. Run: gh auth login")
            return False
        except FileNotFoundError:
            logger.error("✗ GitHub CLI (gh) not installed. Install from: https://cli.github.com/")
            return False
        except Exception as e:
            logger.error(f"Error checking gh CLI: {e}")
            return False

    def _check_gh_copilot_extension(self) -> bool:
        """Check if GitHub Copilot CLI extension is installed."""
        try:
            result = subprocess.run(
                ["gh", "copilot", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("✓ GitHub Copilot CLI extension is installed")
                return True
            logger.error(
                "✗ GitHub Copilot CLI extension not installed.\n"
                "   Install with: gh extension install github/gh-copilot"
            )
            return False
        except Exception as e:
            logger.error(f"Error checking gh copilot extension: {e}\nInstall with: gh extension install github/gh-copilot")
            return False

    def _check_healing_attempt_limit(self, issue_id: str) -> bool:
        """Return True if another attempt is allowed; False when MAX_HEALING_ATTEMPTS is reached."""
        tracking_file = self.repo_path / ".github" / "healing_attempts.jrvs"
        try:
            attempts = document_store.read(tracking_file) if tracking_file.exists() else {}
            current_attempts = attempts.get(str(issue_id), 0)
            if current_attempts >= MAX_HEALING_ATTEMPTS:
                logger.warning(
                    f"⚠️  Maximum healing attempts ({MAX_HEALING_ATTEMPTS}) reached for issue #{issue_id}.\n"
                    f"   Stopping to prevent infinite loop.\n   Manual intervention required."
                )
                return False
            attempts[str(issue_id)] = current_attempts + 1
            tracking_file.parent.mkdir(parents=True, exist_ok=True)
            document_store.write(tracking_file, attempts)
            logger.info(f"✓ Healing attempt {current_attempts + 1}/{MAX_HEALING_ATTEMPTS} for issue #{issue_id}")
            return True
        except Exception as e:
            logger.warning(f"Could not check healing attempt limit: {e}")
            return True  # Allow to proceed if tracking fails

    def _set_github_output(self, name: str, value: str) -> None:
        """Set a GitHub Actions output variable."""
        github_output = os.getenv("GITHUB_OUTPUT")
        if github_output:
            try:
                with open(github_output, 'a') as f:
                    f.write(f"{name}={value}\n")
                logger.info(f"✓ Set GitHub output: {name}={value}")
            except Exception as e:
                logger.warning(f"Could not set GitHub output: {e}")

    def run_with_state_machine(self, pytest_report_path: Optional[str] = None) -> int:
        """Run the state-machine repair loop; returns 0 on success, 1 on failure."""
        logger.info("=" * 60)
        logger.info("JARVIS AUTO-FIXER - Self-Healing State Machine")
        logger.info("Powered by GitHub Copilot CLI")
        logger.info("=" * 60)

        state_machine = SelfHealingStateMachine(limit=MAX_HEALING_ATTEMPTS)
        error_details = ""
        attempted_fixes = []

        issue_body = os.getenv("ISSUE_BODY")
        issue_id = os.getenv("ISSUE_NUMBER") or os.getenv("ISSUE_ID", "unknown")

        # Parse pytest report if provided
        if pytest_report_path and Path(pytest_report_path).exists():
            logger.info(f"\n📊 Reading pytest report: {pytest_report_path}")
            report_data = fix_applier.parse_pytest_report(pytest_report_path)
            error_details = report_data['error_details']
            if report_data['has_failures']:
                normalized = (issue_body or "").strip().lower()
                if not issue_body or normalized in {"test failures detected", ""}:
                    issue_body = report_data['issue_body']
                if report_data['full_error']:
                    state_machine.identify_error(
                        report_data['full_error'], report_data['traceback_info'] or ""
                    )
            else:
                logger.info("No failed tests found in report")
                if not issue_body:
                    logger.error("No issue body and no failed tests")
                    return 1

        if not issue_body:
            logger.error("ISSUE_BODY environment variable is not set and no pytest report")
            return 1
        if not error_details:
            error_details = issue_body[:1000]
        logger.info(f"\n📋 Issue ID: {issue_id}")
        logger.info(f"📋 Issue Body (preview):\n{issue_body[:200]}...")
        logger.info("\n🔒 Checking healing attempt limit...")
        if not self._check_healing_attempt_limit(issue_id):
            logger.error("Exceeded maximum healing attempts - stopping to prevent infinite loop")
            self._set_github_output("final_state", State.FAILED_LIMIT.value)
            self._set_github_output("error_details", "Exceeded maximum cross-run healing attempts")
            self._set_github_output("attempted_fixes", "Maximum attempts reached across multiple workflow runs")
            return 1

        if state_machine.state == State.CHANGE_REQUESTED and not state_machine.error_type:
            state_machine.identify_error(issue_body)
        status = state_machine.get_status()
        logger.info("\n🤖 State Machine Status:")
        logger.info(f"   State: {status['state']}")
        logger.info(f"   Error Type: {status['error_type']}")
        logger.info(f"   Counter: {status['counter']}/{status['limit']}")
        if status['failure_reason']:
            logger.info(f"   Failure Reason: {status['failure_reason']}")

        if state_machine.should_notify_human():
            if state_machine.error_category == ErrorCategory.ENVIRONMENT_ERROR:
                logger.warning(
                    f"\n🌍 [ENVIRONMENT ERROR] Erro de Ambiente detectado: {state_machine.error_type}\n"
                    "O sistema irá registrar no log e pausar em vez de tentar modificar o código."
                )
                self._set_github_output("final_state", state_machine.state.value)
                self._set_github_output("error_details", error_details.replace('\n', '\\n'))
                self._set_github_output(
                    "attempted_fixes",
                    f"Erro de Ambiente ({state_machine.error_type}): nenhuma mutação de código realizada.",
                )
                return 1
            logger.warning(f"\n{state_machine.get_final_message()}")
            self._set_github_output("final_state", state_machine.state.value)
            self._set_github_output("error_details", error_details.replace('\n', '\\n'))
            self._set_github_output("attempted_fixes", "Nenhuma tentativa realizada - erro requer intervenção humana direta")
            return 1

        # Repair cycle
        while state_machine.can_attempt_repair():
            logger.info(f"\n{'=' * 60}")
            logger.info(f"🔧 Repair Attempt {state_machine.counter + 1}/{state_machine.limit}")
            logger.info(f"{'=' * 60}")

            fix_info = pr_manager.attempt_repair(issue_body, issue_id, self.repo_path)
            success = fix_info.get('success', False)
            attempt_num = state_machine.counter + 1
            attempted_fixes.append(
                f"**Tentativa {attempt_num}:**\n"
                f"- Arquivo: {fix_info.get('file', 'Arquivo não especificado')}\n"
                f"- Ação: {fix_info.get('description', 'Correção automática aplicada')}\n"
                f"- Resultado: {'✅ Sucesso' if success else '❌ Falhou'}"
            )

            new_state = state_machine.record_repair_attempt(success)
            if new_state == State.SUCCESS:
                logger.info(f"\n{state_machine.get_final_message()}")
                self._set_github_output("final_state", State.SUCCESS.value)
                self._set_github_output("error_details", error_details.replace('\n', '\\n'))
                self._set_github_output("attempted_fixes", '\n\n'.join(attempted_fixes).replace('\n', '\\n'))
                return 0
            elif new_state == State.FAILED_LIMIT:
                logger.warning(f"\n{state_machine.get_final_message()}")
                self._set_github_output("final_state", State.FAILED_LIMIT.value)
                self._set_github_output("error_details", error_details.replace('\n', '\\n'))
                self._set_github_output("attempted_fixes", '\n\n'.join(attempted_fixes).replace('\n', '\\n'))
                return 1

        # Should not reach here
        logger.warning(f"\n{state_machine.get_final_message()}")
        self._set_github_output("final_state", state_machine.state.value)
        self._set_github_output("error_details", error_details.replace('\n', '\\n'))
        self._set_github_output(
            "attempted_fixes",
            '\n\n'.join(attempted_fixes).replace('\n', '\\n') if attempted_fixes else "Nenhuma tentativa registrada",
        )
        return 1

    def run(self) -> int:
        """Run standard (non-state-machine) repair flow; returns 0 on success, 1 on failure."""
        logger.info("=" * 60)
        logger.info("JARVIS AUTO-FIXER - Self-Healing System")
        logger.info("Powered by GitHub Copilot CLI")
        logger.info("=" * 60)

        issue_body = os.getenv("ISSUE_BODY")
        issue_id = os.getenv("ISSUE_NUMBER") or os.getenv("ISSUE_ID", "unknown")

        if not issue_body:
            logger.error("ISSUE_BODY environment variable is not set")
            return 1

        logger.info(f"\n📋 Issue ID: {issue_id}")
        logger.info(f"📋 Issue Body (preview):\n{issue_body[:200]}...")
        logger.info("\n🔒 Checking healing attempt limit...")
        if not self._check_healing_attempt_limit(issue_id):
            logger.error("Exceeded maximum healing attempts - stopping to prevent infinite loop")
            return 1

        fix_info = pr_manager.attempt_repair(issue_body, issue_id, self.repo_path)
        if fix_info.get('success', False):
            logger.info("\n" + "=" * 60)
            logger.info("✅ AUTO-FIX COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            return 0

        logger.error(f"\n❌ Auto-fix failed: {fix_info.get('description', 'Unknown error')}")
        logger.info("💡 Inclua na issue: caminho do arquivo, palavras-chave e descrição da alteração.")
        return 1


def main() -> None:
    """Entry point for the script."""
    parser = argparse.ArgumentParser(description="Jarvis Auto-Fixer - Self-Healing State Machine")
    parser.add_argument('--state', type=str, help='Path to pytest JSON report file for state machine mode')
    args = parser.parse_args()

    try:
        auto_fixer = AutoFixer()
        if args.state:
            logger.info("Running in State Machine mode")
            exit_code = auto_fixer.run_with_state_machine(args.state)
        else:
            logger.info("Running in Standard mode")
            exit_code = auto_fixer.run()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Auto-fixer interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
