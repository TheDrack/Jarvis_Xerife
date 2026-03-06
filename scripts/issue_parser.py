#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Issue Parser - File detection and issue classification utilities.

Provides standalone functions to classify the type of issue (bug fix,
documentation update, or feature request) and locate the target file
referenced in an error traceback or free-text issue body.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_documentation_request(issue_body: str) -> bool:
    """
    Detect if the issue is requesting a documentation update.

    Args:
        issue_body: The issue body text.

    Returns:
        True if this appears to be a documentation request, False otherwise.
    """
    doc_keywords = [
        'adicionar uma seção',
        'adicionar seção',
        'add a section',
        'add section',
        'update readme',
        'atualizar readme',
        'update documentation',
        'atualizar documentação',
        'add to readme',
        'adicionar ao readme',
        'create section',
        'criar seção',
        'documentation',
        'documentação',
    ]
    issue_lower = issue_body.lower()
    for keyword in doc_keywords:
        if keyword in issue_lower:
            logger.info(f"Detected documentation request: '{keyword}' found in issue")
            return True
    return False


def is_feature_request(issue_body: str) -> bool:
    """
    Detect if the issue is requesting a new feature.

    Args:
        issue_body: The issue body text.

    Returns:
        True if this appears to be a feature request, False otherwise.
    """
    feature_keywords = [
        'implementar',
        'implement',
        'adicionar',
        'add',
        'criar',
        'create',
        'new feature',
        'nova funcionalidade',
        'feature request',
        'solicitação de recurso',
        'enhance',
        'melhorar',
        'improvement',
        'melhoria',
        'facilitar',
        'facilitate',
    ]
    issue_lower = issue_body.lower()
    for keyword in feature_keywords:
        if keyword in issue_lower:
            logger.info(f"Detected feature request: '{keyword}' found in issue")
            return True
    return False


def extract_file_from_error(error_message: str) -> Optional[str]:
    """
    Extract the affected file path from an error message.

    Args:
        error_message: The error message text.

    Returns:
        File path if found, None otherwise.
    """
    patterns = [
        r'File "([^"]+)"',
        r'in file ([^\s]+)',
        r'at ([^\s:]+):',
        r'([^\s]+\.py):\d+:',
        r'([^\s]+\.js):\d+:',
        r'([^\s]+\.ts):\d+:',
    ]
    for pattern in patterns:
        match = re.search(pattern, error_message)
        if match:
            file_path = match.group(1)
            logger.info(f"Extracted file path from traceback: {file_path}")
            return file_path
    logger.warning("Could not extract file path from traceback")
    return None


def extract_common_filename(issue_body: str, repo_path: Path) -> Optional[str]:
    """
    Extract common file names from issue body when no traceback is found.

    Args:
        issue_body: The issue body text.
        repo_path: Root path of the repository.

    Returns:
        File path if a common file is mentioned, None otherwise.
    """
    common_files = {
        'readme': 'README.md',
        'readme.md': 'README.md',
        'requirements': 'requirements.txt',
        'requirements.txt': 'requirements.txt',
        'setup.py': 'setup.py',
        'setup': 'setup.py',
        'dockerfile': 'Dockerfile',
        'docker-compose': 'docker-compose.yml',
        'docker-compose.yml': 'docker-compose.yml',
        'makefile': 'Makefile',
        '.gitignore': '.gitignore',
        'gitignore': '.gitignore',
        'license': 'LICENSE',
        'license.md': 'LICENSE',
        'contributing': 'CONTRIBUTING.md',
        'contributing.md': 'CONTRIBUTING.md',
    }
    issue_lower = issue_body.lower()
    for key, actual_filename in common_files.items():
        if key in issue_lower:
            full_path = repo_path / actual_filename
            if full_path.exists():
                logger.info(f"Found common file mentioned: {key} → {actual_filename}")
                return actual_filename
    return None


def suggest_file_by_keywords(issue_body: str, repo_path: Path) -> Optional[str]:
    """
    Suggest probable files based on keywords in the issue body.

    Args:
        issue_body: The issue body text.
        repo_path: Root path of the repository.

    Returns:
        File path suggestion if keywords match, None otherwise.
    """
    issue_lower = issue_body.lower()

    # Prioritise issue creation/formatting context
    if ('issue' in issue_lower or 'issues' in issue_lower) and any(
        word in issue_lower for word in ['escrita', 'format', 'estrutura', 'criação', 'creation', 'writing']
    ):
        logger.info("Detected issue creation/formatting context")
        fp = 'app/adapters/infrastructure/github_adapter.py'
        if (repo_path / fp).exists():
            logger.info(f"Suggesting file for issue formatting: {fp}")
            return fp

    keyword_suggestions = {
        'github actions': ['.github/workflows/jarvis_code_fixer.yml', '.github/workflows/ci-failure-to-issue.yml'],
        'workflow': ['.github/workflows/jarvis_code_fixer.yml', '.github/workflows/ci-failure-to-issue.yml'],
        'issue': ['app/adapters/infrastructure/github_adapter.py', 'scripts/auto_fixer_logic.py'],
        'issues': ['app/adapters/infrastructure/github_adapter.py', 'scripts/auto_fixer_logic.py'],
        'self-healing': ['scripts/auto_fixer_logic.py', 'app/adapters/infrastructure/github_adapter.py', '.github/workflows/jarvis_code_fixer.yml'],
        'self healing': ['scripts/auto_fixer_logic.py', 'app/adapters/infrastructure/github_adapter.py', '.github/workflows/jarvis_code_fixer.yml'],
        'auto-fixer': ['scripts/auto_fixer_logic.py', '.github/workflows/jarvis_code_fixer.yml'],
        'auto fixer': ['scripts/auto_fixer_logic.py', '.github/workflows/jarvis_code_fixer.yml'],
        'jarvis': ['app/application/services/assistant_service.py', 'app/adapters/infrastructure/github_adapter.py'],
        'api': ['app/adapters/infrastructure/api_server.py', 'app/adapters/infrastructure/api_models.py', 'app/main.py', 'main.py'],
        'payload': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
        'mensagem': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
        'envio': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
        'json': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py'],
        'interface': ['app/adapters/infrastructure/api_models.py', 'app/adapters/infrastructure/api_server.py', 'app/main.py', 'main.py'],
        'frontend': ['app/main.py', 'main.py', 'README.md'],
        'hud': ['app/adapters/infrastructure/api_server.py'],
        'chat': ['app/adapters/infrastructure/api_server.py'],
        'botão': ['app/adapters/infrastructure/api_server.py'],
        'button': ['app/adapters/infrastructure/api_server.py'],
        'transcrição': ['app/adapters/infrastructure/api_server.py'],
        'transcription': ['app/adapters/infrastructure/api_server.py'],
        'voice': ['app/adapters/infrastructure/api_server.py'],
        'voz': ['app/adapters/infrastructure/api_server.py'],
        'input': ['app/adapters/infrastructure/api_server.py'],
        'documentation': ['README.md', 'docs/README.md'],
        'documentação': ['README.md', 'docs/README.md'],
        'readme': ['README.md'],
    }

    for keyword, file_suggestions in keyword_suggestions.items():
        if keyword in issue_lower:
            logger.info(f"Detected keyword '{keyword}' in issue body")
            for suggested_file in file_suggestions:
                if (repo_path / suggested_file).exists():
                    logger.info(f"Suggesting file based on keyword '{keyword}': {suggested_file}")
                    return suggested_file
    return None
