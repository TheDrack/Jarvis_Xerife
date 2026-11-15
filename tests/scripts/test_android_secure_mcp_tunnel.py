from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "android" / "install_secure_mcp_tunnel.sh"
SERVICE = ROOT / "scripts" / "android" / "service" / "run"


class AndroidTunnelPackagingTests(unittest.TestCase):
    def test_installer_builds_android_arm64_with_android_cgo(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('GOOS=android', source)
        self.assertIn('GOARCH=arm64', source)
        self.assertIn('CGO_ENABLED=1', source)
        self.assertIn('CC=clang', source)

    def test_installer_pins_upstream_release_and_uses_official_init(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('TUNNEL_CLIENT_VERSION="v0.0.20"', source)
        self.assertIn('sample_mcp_remote_no_auth', source)
        self.assertIn('--mcp-server-url', source)
        self.assertIn('env:CONTROL_PLANE_API_KEY', source)

    def test_service_reads_private_key_file_without_printing_it(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn('CONTROL_PLANE_API_KEY', source)
        self.assertIn('chmod 600', source)
        self.assertIn('exec "$CLIENT" run', source)
        self.assertNotIn('echo "$CONTROL_PLANE_API_KEY"', source)

    def test_service_waits_for_local_mcp_and_binds_no_public_listener(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn('127.0.0.1', source)
        self.assertIn('MCP_LOCAL_HOST', source)
        self.assertIn('MCP_LOCAL_PORT', source)


if __name__ == "__main__":
    unittest.main()
