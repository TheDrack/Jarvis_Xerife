#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests to validate the workflow fixes for metabolism and auto-evolution.

Validates:
1. metabolism_analyzer.py produces all required GITHUB_OUTPUT fields
2. evolution_mutator.py handles missing cap_id gracefully
3. AutoEvolutionServiceV2 integration basics
4. services package importable without optional dependencies (sqlmodel, etc.)
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def test_metabolism_analyzer_required_outputs():
    """metabolism_analyzer.py must write all required fields to GITHUB_OUTPUT."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        output_file = f.name

    try:
        env = os.environ.copy()
        env['GITHUB_OUTPUT'] = output_file

        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / 'scripts' / 'metabolism_analyzer.py'),
                '--intent', 'test',
                '--instruction', 'Test the analyzer',
                '--context', 'Test context with sufficient length to pass validation',
                '--event-type', 'test',
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        with open(output_file, 'r') as f:
            outputs = f.read()

        assert result.returncode == 0, (
            f"metabolism_analyzer.py exited with code {result.returncode}.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )
        assert 'requires_human=' in outputs, "Missing required output: requires_human"
        assert 'intent_type=' in outputs, "Missing required output: intent_type"
        assert 'impact_type=' in outputs, "Missing required output: impact_type"
        assert 'mutation_strategy=' in outputs, "Missing required output: mutation_strategy"

        for line in outputs.splitlines():
            if line.startswith('mutation_strategy='):
                value = line.split('=', 1)[1]
                assert value != 'None', "mutation_strategy must not be the string 'None'"

    finally:
        if os.path.exists(output_file):
            os.unlink(output_file)


def test_metabolism_analyzer_escalates_on_short_context():
    """When context is too short the analyzer should escalate (requires_human=true)."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        output_file = f.name

    try:
        env = os.environ.copy()
        env['GITHUB_OUTPUT'] = output_file

        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / 'scripts' / 'metabolism_analyzer.py'),
                '--intent', 'x',
                '--instruction', 'y',
                '--context', '',
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        with open(output_file, 'r') as f:
            outputs = f.read()

        assert result.returncode == 0, (
            f"metabolism_analyzer.py exited with code {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )
        assert 'requires_human=true' in outputs, (
            "Short context should force escalation (requires_human=true)"
        )

    finally:
        if os.path.exists(output_file):
            os.unlink(output_file)


def test_evolution_mutator_missing_cap_id():
    """evolution_mutator.py must exit non-zero when no cap_id can be determined."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        output_file = f.name

    try:
        env = os.environ.copy()
        env['GITHUB_OUTPUT'] = output_file
        env.pop('ISSUE_BODY', None)  # Ensure no cap-id can be inferred

        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / 'scripts' / 'evolution_mutator.py'),
                '--strategy', 'minimal_change',
                '--intent', 'test',
                '--impact', 'test',
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        assert result.returncode != 0, (
            "evolution_mutator.py should exit non-zero when no cap_id is provided"
        )

    finally:
        if os.path.exists(output_file):
            os.unlink(output_file)


def test_auto_evolution_service():
    """AutoEvolutionServiceV2 must be importable and respond to basic queries."""
    from app.application.services.auto_evolutionV2 import AutoEvolutionServiceV2  # noqa: PLC0415

    service = AutoEvolutionServiceV2()

    is_auto = service.is_auto_evolution_pr("[Auto-Evolution] Test PR")
    assert is_auto is True, "is_auto_evolution_pr() should detect auto-evolution PRs"

    is_not_auto = service.is_auto_evolution_pr("Fix: regular bug fix")
    assert is_not_auto is False, "is_auto_evolution_pr() should not match regular PRs"


def test_services_package_importable_without_sqlmodel():
    """app.application.services package must be importable even when sqlmodel is absent.

    This is critical for the self-healing workflow where only a minimal set of
    packages is installed.  The package __init__.py must guard its optional imports.

    We test this by launching a subprocess with sqlmodel *blocked* from importation,
    confirming that both the services package and MetabolismCore are still importable.
    """
    code = (
        "import sys, types\n"
        # Block sqlmodel at the importer level
        "sys.modules['sqlmodel'] = None\n"
        "import app.application.services\n"
        "from app.application.services.metabolism_core import MetabolismCore\n"
        "assert MetabolismCore is not None, 'MetabolismCore must be importable'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        "app.application.services must be importable without sqlmodel.\n"
        f"stderr: {result.stderr}\nstdout: {result.stdout}"
    )

