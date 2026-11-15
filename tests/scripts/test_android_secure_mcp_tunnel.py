from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "android" / "install_secure_mcp_tunnel.sh"
CONFIGURER = ROOT / "scripts" / "android" / "configure_secure_mcp_tunnel.sh"
SERVICE = ROOT / "scripts" / "android" / "service" / "run"
LOG_SERVICE = ROOT / "scripts" / "android" / "service" / "log-run"
MCP_SERVICE = ROOT / "scripts" / "android" / "service" / "mcp-run"
MCP_LOG_SERVICE = ROOT / "scripts" / "android" / "service" / "mcp-log-run"
SHELL_CONFIGURER = ROOT / "scripts" / "android" / "configure_termux_shell.sh"
MCP_SERVER = ROOT / "app" / "adapters" / "edge" / "jarvis_android_mcp.py"


class AndroidTunnelPackagingTests(unittest.TestCase):
    def test_installer_builds_android_arm64_with_android_cgo(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('TUNNEL_CLIENT_VERSION="v0.0.20"', source)
        self.assertIn("GOOS=android", source)
        self.assertIn("GOARCH=arm64", source)
        self.assertIn("CGO_ENABLED=1", source)
        self.assertIn("CC=clang", source)

    def test_installer_uses_single_backslash_for_shell_line_continuations(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("\\\\\n", source, "Shell continuations must use exactly one trailing backslash.")

    def test_installer_provisions_isolated_android_mcp_runtime_and_service(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("python -m venv --without-pip", source)
        self.assertIn("python-pip", source)
        self.assertIn('python -m pip --python "$MCP_VENV/bin/python" install', source)
        self.assertNotIn('install --upgrade pip', source)
        self.assertIn('"$MCP_VENV/bin/python" -c', source)
        self.assertIn("mcp>=1.30.0,<2", source)
        self.assertIn("scripts/android/service/mcp-run", source)
        self.assertIn('MCP_SERVICE_NAME="jarvis-android-mcp"', source)
        self.assertIn("MCP_HOST=127.0.0.1", source)
        self.assertIn('sv up "$MCP_SERVICE_LINK"', source)

    def test_installer_preserves_existing_tunnel_configuration_and_secrets(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('if [ -f "$ENV_FILE" ]; then', source)
        self.assertIn('. "$ENV_FILE"', source)
        self.assertIn('[ "$MCP_LOCAL_HOST" = "127.0.0.1" ]', source)
        self.assertIn('if [ ! -f "$ENV_FILE" ]; then', source)
        self.assertIn('if [ ! -e "$SERVICE_LINK" ]; then', source)
        self.assertIn('elif [ ! -L "$SERVICE_LINK" ]; then', source)
        self.assertNotIn("rm -rf", source)

    def test_configurator_uses_private_key_reference_and_newline(self):
        source = CONFIGURER.read_text(encoding="utf-8")
        self.assertIn("sample_mcp_remote_no_auth", source)
        self.assertIn("--mcp-server-url", source)
        self.assertIn("env:CONTROL_PLANE_API_KEY", source)
        self.assertIn("printf '%s\\n'", source)

    def test_tunnel_service_accepts_runtime_key_without_trailing_newline(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn(
            'IFS= read -r CONTROL_PLANE_API_KEY < "$SECRET_FILE" || [ -n "$CONTROL_PLANE_API_KEY" ]',
            source,
        )

        bash = shutil.which("bash")
        self.assertIsNotNone(bash, "A real Bash executable is required for runtime-key loading tests.")
        with tempfile.TemporaryDirectory() as temporary_directory:
            secret_file = Path(temporary_directory) / "runtime-key"
            secret_file.write_bytes(b"x" * 165)
            result = subprocess.run(
                [
                    bash,
                    "-c",
                    'set -Eeuo pipefail; CONTROL_PLANE_API_KEY=""; '
                    'IFS= read -r CONTROL_PLANE_API_KEY < "$1" || [ -n "$CONTROL_PLANE_API_KEY" ]; '
                    '[ "${#CONTROL_PLANE_API_KEY}" -ge 20 ]',
                    "bash",
                    str(secret_file),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_tunnel_service_waits_for_local_mcp_before_starting_tunnel(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", source)
        self.assertIn("MCP_LOCAL_HOST", source)
        self.assertIn("MCP_LOCAL_PORT", source)
        self.assertIn("ready=1", source)
        self.assertLess(source.index("ready=1"), source.index('exec "$CLIENT" run'))

    def test_android_mcp_service_is_loopback_only_and_uses_isolated_python(self):
        source = MCP_SERVICE.read_text(encoding="utf-8")
        self.assertIn('MCP_HOST="${MCP_HOST:-127.0.0.1}"', source)
        self.assertIn('[ "$MCP_HOST" = "127.0.0.1" ]', source)
        self.assertIn('exec "$PYTHON" -m app.adapters.edge.jarvis_android_mcp', source)
        self.assertNotIn("eval ", source)

    def test_mcp_server_exposes_streamable_http_and_read_only_tools(self):
        source = MCP_SERVER.read_text(encoding="utf-8")
        self.assertIn("FastMCP(", source)
        self.assertIn('"Jarvis Android"', source)
        self.assertIn("mcp.streamable_http_app()", source)
        self.assertIn('Mount("/",', source)
        self.assertIn('"127.0.0.1"', source)
        for tool in ("android_device_status", "android_battery_status", "android_wifi_status"):
            self.assertIn(tool, source)


    def test_termux_shell_opt_in_script_updates_private_config_and_restarts_service(self):
        source = SHELL_CONFIGURER.read_text(encoding="utf-8")
        self.assertIn('enable) VALUE=1 ;;', source)
        self.assertIn('disable) VALUE=0 ;;', source)
        self.assertIn('chmod 600 "$TEMP_FILE"', source)
        self.assertIn('sv restart "$SERVICE_LINK"', source)
        self.assertNotIn("pairing_code", source)
        mcp_source = MCP_SERVICE.read_text(encoding="utf-8")
        self.assertIn('export JARVIS_ANDROID_SHELL_ENABLED="${JARVIS_ANDROID_SHELL_ENABLED:-0}"', mcp_source)

    def test_android_mcp_registers_termux_shell_session_tools(self):
        source = MCP_SERVER.read_text(encoding="utf-8")
        self.assertIn("register_termux_shell_tools(mcp)", source)
        self.assertIn("android_shell_exec", source)
        self.assertIn("JARVIS_ANDROID_SHELL_ENABLED", source)

    def test_shell_scripts_parse_without_syntax_errors(self):
        bash = shutil.which("bash")
        if os.name == "nt":
            git = shutil.which("git")
            if git:
                git_root = Path(git).resolve().parents[1]
                git_bash = git_root / "bin" / "bash.exe"
                if git_bash.is_file():
                    bash = str(git_bash)

        self.assertIsNotNone(bash, "A real Bash executable is required for shell syntax checks.")
        version = subprocess.run([bash, "--version"], capture_output=True, text=True, check=False)
        self.assertEqual(version.returncode, 0, msg=f"Selected Bash executable is not runnable: {bash}\\nstdout: {version.stdout}\\nstderr: {version.stderr}")
        self.assertIn("GNU bash", version.stdout, msg=f"Unexpected Bash executable: {bash}")

        for path in (INSTALLER, CONFIGURER, SHELL_CONFIGURER, SERVICE, LOG_SERVICE, MCP_SERVICE, MCP_LOG_SERVICE):
            result = subprocess.run(
                [bash, "-n"], input=path.read_text(encoding="utf-8"),
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, msg=f"{path}: bash={bash}\\nstdout: {result.stdout}\\nstderr: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
