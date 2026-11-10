"""Static contract tests for the Linux provisioning kit's network and data boundaries."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_linux_api_unit_pins_effective_bind_address_to_loopback():
    unit = (ROOT / "linux/systemd/jarvis-api.service").read_text(encoding="utf-8")

    assert "ExecStart=/usr/bin/env API_HOST=127.0.0.1 " in unit


def test_provisioner_expands_home_in_generated_database_paths():
    script = (ROOT / "linux/provision-jarvis-os.sh").read_text(encoding="utf-8")

    assert 'cat > "$ENV_FILE" <<ENVEOF' in script
    assert "JARVIS_DEVICES_DB=${HOME}/.local/share/jarvis/jarvis.db" in script
    assert "JARVIS_GEOINT_DB=${HOME}/.local/share/jarvis/geoint.sqlite" in script
    assert "JARVIS_GRAPH_DB=${HOME}/.local/share/jarvis/jarvis_graph.sqlite" in script
    assert "cat > \"$ENV_FILE\" <<'ENVEOF'" not in script


def test_linux_verifier_checks_effective_api_bind_address():
    verifier = (ROOT / "linux/verify-jarvis-os.sh").read_text(encoding="utf-8")

    assert "systemctl --user show jarvis-api.service" in verifier
    assert "API_HOST=127.0.0.1" in verifier
