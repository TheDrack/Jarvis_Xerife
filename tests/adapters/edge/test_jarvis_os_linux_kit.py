"""Static contract tests for the Linux provisioning kit's network and data boundaries."""
from pathlib import Path


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
