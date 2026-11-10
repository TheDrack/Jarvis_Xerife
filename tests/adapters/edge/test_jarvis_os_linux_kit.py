"""Static contract tests for the Linux provisioning kit's network and data boundaries."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]


def test_linux_api_unit_pins_effective_bind_address_to_loopback():
    unit = (ROOT / "linux/systemd/jarvis-api.service").read_text(encoding="utf-8")

    assert "ExecStart=/usr/bin/env API_HOST=127.0.0.1 " in unit


def test_provisioner_expands_home_in_generated_database_paths():
    script = (ROOT / "linux/provision-jarvis-os.sh").read_text(encoding="utf-8")

    assert 'cat > "$ENV_FILE" <<\'ENVEOF\'' in script
    assert "awk '!/^JARVIS_(DEVICES|GEOINT|GRAPH)_DB=/'" in script
    assert 'printf \'JARVIS_DEVICES_DB="%s"\\nJARVIS_GEOINT_DB="%s"\\nJARVIS_GRAPH_DB="%s"\\n\'' in script
    assert '"$HOME/.local/share/jarvis/jarvis.db"' in script
    assert '"$HOME/.local/share/jarvis/geoint.sqlite"' in script
    assert '"$HOME/.local/share/jarvis/jarvis_graph.sqlite"' in script


def test_linux_verifier_checks_effective_api_bind_address():
    verifier = (ROOT / "linux/verify-jarvis-os.sh").read_text(encoding="utf-8")

    assert "systemctl --user show jarvis-api.service" in verifier
    assert "API_HOST=127.0.0.1" in verifier


def test_mcp_unit_uses_authenticated_linux_entrypoint():
    unit = (ROOT / "linux/systemd/jarvis-mcp.service").read_text(encoding="utf-8")

    assert "app.adapters.edge.jarvis_linux_mcp" in unit
    assert "app.adapters.edge.jarvis_desktop_mcp" not in unit


def test_provisioner_protects_credentials_directory_and_temp_copy():
    script = (ROOT / "linux/provision-jarvis-os.sh").read_text(encoding="utf-8")

    assert script.index("umask 077") < script.index('mkdir -p "$ENV_DIR"')
    assert 'chmod 700 "$ENV_DIR"' in script
    assert 'trap \'rm -f "$runtime_env_tmp" "${runtime_env_tmp}.next"\' EXIT' in script
    assert 'chmod 600 "$runtime_env_tmp"' in script
    assert 'chmod 600 "$ENV_FILE"' in script
    assert "secrets.token_urlsafe(48)" in script
    assert 'JARVIS_DESKTOP_AUTH_TOKEN=' in script


def test_mcp_asgi_wrapper_dependency_is_available_in_linux_profile():
    requirements = (ROOT / "linux/requirements-linux.txt").read_text(encoding="utf-8")
    edge_requirements = (ROOT / "requirements/edge.txt").read_text(encoding="utf-8")

    assert "mcp>=1.30,<2" in requirements
    assert "mcp>=1.30,<2" in edge_requirements


def test_linux_verifier_checks_mcp_bearer_gate():
    verifier = (ROOT / "linux/verify-jarvis-os.sh").read_text(encoding="utf-8")

    assert "JARVIS_DESKTOP_AUTH_TOKEN" in verifier
    assert "jarvis_linux_mcp" in verifier
    assert "mcp_status" in verifier
    assert 'if [ "$mcp_status" = "401" ]' in verifier


def test_linux_verifier_has_valid_bash_syntax():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is unavailable on this runner")

    verifier = ROOT / "linux/verify-jarvis-os.sh"
    result = subprocess.run(
        [bash, "-n", str(verifier)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_linux_verifier_contains_one_complete_environment_and_summary_block():
    verifier = (ROOT / "linux/verify-jarvis-os.sh").read_text(encoding="utf-8")

    assert verifier.count('if [ -f "$ENV_FILE" ]; then') == 1
    assert verifier.count("printf '\\nResumo:") == 1
    assert 'if grep -qE \'^JARVIS_DESKTOP_AUTH_TOKEN="?[^\"]{32,}"?$\' "$ENV_FILE"; then' in verifier


def test_harden_network_does_not_expose_ssh_on_public_interfaces():
    script = (ROOT / "linux/provision-jarvis-os.sh").read_text(encoding="utf-8")

    assert "$SUDO ufw allow in on tailscale0 to any port 22 proto tcp" in script
    assert "$SUDO ufw allow 22/tcp" not in script


def test_harden_network_removes_legacy_global_ssh_rules():
    script = (ROOT / "linux/provision-jarvis-os.sh").read_text(encoding="utf-8")

    assert "$SUDO ufw --force delete allow 22/tcp" in script
    assert "$SUDO ufw --force delete allow ssh" in script
