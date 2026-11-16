from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONFIGURER = ROOT / "scripts" / "android" / "configure_termux_shell.sh"


class AndroidShellTunnelRefreshTests(unittest.TestCase):
    def test_shell_toggle_restarts_active_tunnel_after_restarting_mcp(self):
        source = CONFIGURER.read_text(encoding="utf-8")

        self.assertIn(
            'TUNNEL_SERVICE_LINK="$PREFIX/var/service/jarvis-secure-mcp-tunnel"',
            source,
        )
        mcp_restart = source.index('sv restart "$SERVICE_LINK"')
        tunnel_status = source.index('sv status "$TUNNEL_SERVICE_LINK"')
        tunnel_restart = source.index('sv restart "$TUNNEL_SERVICE_LINK"')

        self.assertLess(mcp_restart, tunnel_status)
        self.assertLess(tunnel_status, tunnel_restart)
        self.assertIn('if sv status "$TUNNEL_SERVICE_LINK" >/dev/null 2>&1; then', source)


if __name__ == "__main__":
    unittest.main()
