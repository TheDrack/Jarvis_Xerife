#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix Applier - GitHub Copilot interaction, file I/O, and fix validation.

Provides utilities for interacting with the GitHub Copilot CLI, reading and
writing files, validating generated fixes with pytest, and parsing pytest
JSON reports for use by the self-healing state machine.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Maximum log size to prevent terminal overflow (5000 characters)
MAX_LOG_SIZE = 5000
# Maximum prompt size for code suggestions (allows more context)
MAX_PROMPT_SIZE = MAX_LOG_SIZE * 2  # 10000 characters
# Maximum size for error message in fix prompts
MAX_ERROR_SIZE_IN_FIX = 1000
# Minimum valid code length for sanity check
MIN_VALID_CODE_LENGTH = 50
# Prefixes that Copilot might use in output (may need updates based on CLI changes)
COPILOT_OUTPUT_PREFIXES = ["Suggestion:", "Here's the fix:", "Fixed code:", "Solution:"]


def truncate_log(log_text: str, max_size: int = MAX_LOG_SIZE) -> str:
    """Truncate log text to prevent terminal character limit issues."""
    if len(log_text) <= max_size:
        return log_text
    truncated = log_text[-max_size:]
    return f"[Log truncated - showing last {max_size} characters]\n...\n{truncated}"


def sanitize_prompt(prompt: str) -> str:
    """Sanitize prompt text for gh copilot CLI commands, removing shell-unsafe characters."""
    sanitized = prompt.replace('\n', ' ').replace('\r', ' ')
    sanitized = re.sub(r'\s+', ' ', sanitized)
    # Keep only printable ASCII (32-126); strips Unicode to ensure reliable CLI execution
    sanitized = re.sub(r'[^\x20-\x7E]', '', sanitized)
    return sanitized.strip()


def read_file_content(file_path: str, repo_path: Path) -> Optional[str]:
    """Read content from a file, returning None if it does not exist."""
    try:
        full_path = repo_path / file_path
        if not full_path.exists():
            logger.error(f"File not found: {full_path}")
            return None
        content = full_path.read_text(encoding='utf-8')
        logger.info(f"Read {len(content)} characters from {file_path}")
        return content
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return None


def call_gh_copilot_explain(error_message: str, repo_path: Path) -> Optional[str]:
    """
    Use GitHub Copilot CLI to explain an error.

    Args:
        error_message: The error message to explain.
        repo_path: Root path of the repository (used as cwd).

    Returns:
        Explanation from Copilot or None if the call fails.
    """
    try:
        sanitized = sanitize_prompt(truncate_log(error_message))
        prompt = f"Explain this error: {sanitized}"
        result = subprocess.run(
            ["gh", "copilot", "--model", "claude-3.5-sonnet", "--", "-p", prompt],
            capture_output=True, text=True, timeout=60, cwd=repo_path,
        )
        if result.returncode == 0:
            explanation = result.stdout.strip()
            logger.info(f"✓ Received explanation from GitHub Copilot ({len(explanation)} chars)")
            return explanation
        logger.error(f"GitHub Copilot explain failed: {result.stderr}")
        return None
    except Exception as e:
        logger.error(f"Error calling gh copilot explain: {e}")
        return None


def call_gh_copilot_suggest(prompt: str, repo_path: Path) -> Optional[str]:
    """
    Use GitHub Copilot CLI to get code suggestions.

    Args:
        prompt: The prompt describing what code is needed.
        repo_path: Root path of the repository (used as cwd).

    Returns:
        Suggested code from Copilot or None if the call fails.
    """
    try:
        sanitized = sanitize_prompt(truncate_log(prompt, max_size=MAX_PROMPT_SIZE))
        full_prompt = f"Suggest a solution for: {sanitized}"
        result = subprocess.run(
            ["gh", "copilot", "--model", "claude-3.5-sonnet", "--", "-p", full_prompt],
            capture_output=True, text=True, timeout=60, cwd=repo_path,
        )
        if result.returncode == 0:
            suggestion = result.stdout.strip()
            logger.info(f"✓ Received suggestion from GitHub Copilot ({len(suggestion)} chars)")
            return suggestion
        logger.error(f"GitHub Copilot suggest failed: {result.stderr}")
        return None
    except Exception as e:
        logger.error(f"Error calling gh copilot suggest: {e}")
        return None


def get_fixed_code_with_copilot(
    error_message: str,
    code: str,
    file_path: str,
    repo_path: Path,
    is_doc_request: bool = False,
    is_feature: bool = False,
) -> Optional[str]:
    """
    Get fixed code using GitHub Copilot CLI.

    Args:
        error_message: The error message or user request.
        code: The current file content.
        file_path: The path to the file being fixed.
        repo_path: Root path of the repository.
        is_doc_request: Whether this is a documentation update request.
        is_feature: Whether this is a feature request.

    Returns:
        Fixed code or None if the operation fails.
    """
    try:
        logger.info("🤖 Getting error explanation from GitHub Copilot...")
        explanation = call_gh_copilot_explain(error_message, repo_path)
        if explanation:
            logger.info(f"📝 Copilot explanation:\n{explanation[:300]}...")

        logger.info("🤖 Generating fix with GitHub Copilot...")
        with tempfile.NamedTemporaryFile(mode='w', suffix=Path(file_path).suffix, delete=False) as f:
            f.write(code)
            temp_code_file = f.name

        try:
            fix_prompt = (
                f"Fix this code error:\n\nError: {truncate_log(error_message, MAX_ERROR_SIZE_IN_FIX)}"
                f"\n\nFile: {file_path}\n\nShow me the corrected version of this file: {temp_code_file}"
            )
            result = subprocess.run(
                ["gh", "copilot", "--model", "claude-3.5-sonnet", "--", "-p", sanitize_prompt(fix_prompt)],
                capture_output=True, text=True, timeout=90, cwd=repo_path,
            )
            if result.returncode != 0:
                logger.error(f"GitHub Copilot suggest for fix failed: {result.stderr}")
                return None

            output = result.stdout.strip()
            code_blocks = re.findall(r'```(?:\w+)?\n(.*?)\n```', output, re.DOTALL)
            if code_blocks:
                fixed_code = code_blocks[0].strip()
                logger.info(f"✓ Extracted fixed code from Copilot output ({len(fixed_code)} chars)")
                return fixed_code

            logger.warning("No code blocks found in Copilot output, using full output")
            cleaned = output
            for prefix in COPILOT_OUTPUT_PREFIXES:
                if prefix in cleaned:
                    cleaned = cleaned.split(prefix, 1)[1].strip()
            if len(cleaned) > MIN_VALID_CODE_LENGTH:
                return cleaned
            logger.error(f"Copilot output too short ({len(cleaned)} chars, min {MIN_VALID_CODE_LENGTH})")
            return None
        finally:
            try:
                os.unlink(temp_code_file)
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error getting fixed code from Copilot: {e}")
        return None


def apply_fix(file_path: str, fixed_code: str, repo_path: Path) -> bool:
    """Write fixed_code to file_path, creating parent directories as needed."""
    try:
        full_path = repo_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(fixed_code, encoding='utf-8')
        logger.info(f"✓ Applied fix to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error applying fix to {file_path}: {e}")
        return False


def run_pytest(repo_path: Path) -> bool:
    """Run pytest (verbose) and return True if all tests pass."""
    try:
        result = subprocess.run(
            ["pytest", "--tb=short", "-v"],
            cwd=repo_path, capture_output=True, text=True, timeout=300,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error("Pytest timed out")
        return False
    except Exception as e:
        logger.error(f"Error running pytest: {e}")
        return False


def parse_pytest_report(report_path: str) -> Dict[str, Any]:
    """
    Parse a pytest JSON report and extract error information.

    Args:
        report_path: Path to the pytest JSON report file.

    Returns:
        Dictionary with keys:
            - issue_body (Optional[str]): Supplement/replacement for ISSUE_BODY env var.
            - error_details (str): Human-readable error details.
            - full_error (Optional[str]): Combined error for state machine classification.
            - traceback_info (Optional[str]): Traceback string.
            - has_failures (bool): Whether failed tests were found.
    """
    result: Dict[str, Any] = {
        'issue_body': None,
        'error_details': '',
        'full_error': None,
        'traceback_info': None,
        'has_failures': False,
    }
    try:
        with open(report_path, 'r') as f:
            report = json.load(f)

        failed_tests = [t for t in report.get('tests', []) if t.get('outcome') == 'failed']
        if not failed_tests:
            logger.info("No failed tests found in report")
            return result

        logger.info(f"Found {len(failed_tests)} failed test(s)")
        first_failure = failed_tests[0]

        error_msg_raw = first_failure.get('call', {}).get('longrepr', '')
        if isinstance(error_msg_raw, dict):
            error_msg = str(error_msg_raw.get('reprcrash', {}).get('message', ''))
        elif isinstance(error_msg_raw, list):
            error_msg = '\n'.join(str(item) for item in error_msg_raw)
        else:
            error_msg = str(error_msg_raw)

        traceback_raw = first_failure.get('call', {}).get('crash', {}).get('message', '')
        traceback_info = str(traceback_raw) if isinstance(traceback_raw, (dict, list)) else str(traceback_raw)

        result.update({
            'issue_body': f"Test failure:\n{error_msg}\n\nTraceback:\n{traceback_info}",
            'error_details': f"Test: {first_failure.get('nodeid', 'Unknown')}\n{error_msg}\n\nTraceback:\n{traceback_info}",
            'full_error': f"{error_msg}\n{traceback_info}",
            'traceback_info': traceback_info,
            'has_failures': True,
        })
    except Exception as e:
        logger.warning(f"Failed to parse pytest report: {e}")
        result['error_details'] = f"Failed to parse pytest report: {str(e)}"
    return result
