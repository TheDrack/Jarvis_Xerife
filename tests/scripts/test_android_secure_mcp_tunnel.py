from pathlib import Path
import os
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "android" / "install_secure_mcp_tunnel.sh"
CONFIGURER = ROOT / "scripts" / "android" / "configure_secure_mcp_tunnel.sh"
SERVICE = ROOT / "scripts" / "android" / "service" / "run"
LOG_SERVICE = ROOT / "scripts" / "android" / "service" / "log-run"


class AndroidTunnelPackagingTests(unittest.TestCase):
    def test_installer_builds_android_arm64_with_android_cgo(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("GOOS=android", source)
        self.assertIn("GOARCH=arm64", source)
        self.assertIn("CGO_ENABLED=1", source)
        self.assertIn("CC=clang", source)

    def test_installer_pins_upstream_release_and_uses_official_init(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('TUNNEL_CLIENT_VERSION="v0.0.20"', source)
        self.assertIn("sample_mcp_remote_no_auth", CONFIGURER.read_text(encoding="utf-8"))
        self.assertIn("--mcp-server-url", CONFIGURER.read_text(encoding="utf-8"))
        self.assertIn("env:CONTROL_PLANE_API_KEY", CONFIGURER.read_text(encoding="utf-8"))

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
        version = subprocess.run(
            [bash, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            version.returncode,
            0,
            msg=(
                f"Selected Bash executable is not runnable: {bash}\n"
                f"stdout: {version.stdout}\nstderr: {version.stderr}"
            ),
        )
        self.assertIn("GNU bash", version.stdout, msg=f"Unexpected Bash executable: {bash}")

        for path in (INSTALLER, CONFIGURER, SERVICE, LOG_SERVICE):
            # Feed source over stdin and explicitly select Git for Windows Bash.
            # The plain PATH entry may resolve to the WSL launcher on Windows runners.
            result = subprocess.run(
                [bash, "-n"],
                input=path.read_text(encoding="utf-8"),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=(
                    f"{path}: bash={bash}\n"
                    f"stdout: {result.stdout}\nstderr: {result.stderr}"
                ),
            )

    def test_configurator_terminates_private_key_file_with_newline(self):
        source = CONFIGURER.read_text(encoding="utf-8")
        self.assertIn("printf '%s\\n'", source)

    def test_service_reads_private_key_file_without_printing_it(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("CONTROL_PLANE_API_KEY", source)
        self.assertIn("chmod 600", source)
        self.assertIn('exec "$CLIENT" run', source)
        self.assertNotIn('echo "$CONTROL_PLANE_API_KEY"', source)
        self.assertNotIn("--health-listen-addr", source)

    def test_service_waits_for_local_mcp_before_starting_tunnel(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", source)
        self.assertIn("MCP_LOCAL_HOST", source)
        self.assertIn("MCP_LOCAL_PORT", source)
        self.assertLess(source.index("ready=1"), source.index('exec "$CLIENT" run'))


if __name__ == "__main__":
    unittest.main()
