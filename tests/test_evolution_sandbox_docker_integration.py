"""Real Docker integration test for candidate execution isolation.

CI builds the sandbox image and sets EVOLUTION_SANDBOX_IMAGE. Local runs without
that image skip this integration test; the mocked security-contract tests still run.
"""
import os

import pytest

from app.application.services.evolution_sandbox import EvolutionSandbox


@pytest.mark.skipif(
    not os.getenv("EVOLUTION_SANDBOX_IMAGE"),
    reason="hardened Docker image is only provisioned in the PR validation workflow",
)
def test_candidate_is_applied_without_host_secrets_filesystem_or_network(tmp_path, monkeypatch):
    repository = tmp_path / "candidate-repository"
    tests_dir = repository / "tests"
    tests_dir.mkdir(parents=True)

    host_secret = tmp_path / "host-secret.txt"
    host_secret.write_text("host-only-secret", encoding="utf-8")

    monkeypatch.setenv("GROQ_API_KEY", "host-provider-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "host-github-secret")
    monkeypatch.setenv("GH_TOKEN", "host-gh-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "host-supabase-secret")

    candidate_code = f'''import os
import socket
from pathlib import Path

def candidate_marker():
    forbidden = (
        "GROQ_API_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "SUPABASE_SERVICE_ROLE_KEY",
    )
    assert all(not os.environ.get(name) for name in forbidden)
    assert not Path({str(host_secret)!r}).exists()

    connection = socket.socket()
    connection.settimeout(2)
    try:
        network_result = connection.connect_ex(("1.1.1.1", 443))
    finally:
        connection.close()
    assert network_result != 0
    return "candidate-was-applied"
'''
    (repository / "candidate.py").write_text(candidate_code, encoding="utf-8")
    (tests_dir / "test_candidate.py").write_text(
        "from candidate import candidate_marker\n"
        "def test_candidate_was_applied_inside_isolation():\n"
        "    assert candidate_marker() == 'candidate-was-applied'\n",
        encoding="utf-8",
    )

    sandbox = EvolutionSandbox()
    sandbox.repository_root = repository
    sandbox.image = os.environ["EVOLUTION_SANDBOX_IMAGE"]
    result = sandbox.test_proposal(candidate_code, "candidate.py")

    assert result["passed"] is True, result["test_output"]
    assert "1 passed" in result["test_output"]
