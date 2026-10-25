import ipaddress
import unittest
from unittest.mock import patch, Mock

from app.adapters.edge.network_discovery_adapter import (
    _private_network,
    discover_devices,
    inspect_private_address,
)


class NetworkDiscoveryAdapterTests(unittest.TestCase):
    def test_rejects_public_scope(self):
        with self.assertRaises(ValueError):
            _private_network("8.8.8.0/24")

    def test_rejects_scope_larger_than_slash_24(self):
        with self.assertRaises(ValueError):
            _private_network("192.168.0.0/16")

    def test_accepts_private_slash_24(self):
        self.assertEqual(str(_private_network("192.168.1.0/24")), "192.168.1.0/24")

    @patch("app.adapters.edge.network_discovery_adapter.subprocess.run")
    def test_arp_discovery_is_read_only_and_filters_to_scope(self, run):
        run.return_value = Mock(
            stdout="Interface: 192.168.1.4 --- 0x7\n  192.168.1.10  aa-bb-cc-dd-ee-ff  dynamic\n  192.168.2.10  11-22-33-44-55-66 dynamic\n",
            returncode=0,
        )
        with patch("app.adapters.edge.network_discovery_adapter.platform.system", return_value="Windows"):
            result = discover_devices("192.168.1.0/24")
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["devices"][0]["ip"], "192.168.1.10")
        self.assertEqual(result["active_probes_sent"], 0)
        run.assert_called_once()
        self.assertFalse(run.call_args.kwargs.get("shell", True))

    def test_inspection_rejects_public_address(self):
        self.assertFalse(inspect_private_address("1.1.1.1")["success"])

    @patch("app.adapters.edge.network_discovery_adapter.socket.gethostbyaddr")
    def test_private_address_inspection_does_not_scan_ports(self, reverse):
        reverse.return_value = ("router.local", [], ["192.168.1.1"])
        result = inspect_private_address("192.168.1.1")
        self.assertTrue(result["success"])
        self.assertFalse(result["ports_scanned"])


if __name__ == "__main__":
    unittest.main()

