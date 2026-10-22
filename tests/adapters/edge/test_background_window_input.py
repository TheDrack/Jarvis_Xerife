import unittest

from app.adapters.edge.background_window_input import click_window_background, pack_point


class BackgroundWindowInputTests(unittest.TestCase):
    def test_pack_point_encodes_client_coordinates(self):
        self.assertEqual(pack_point(12, 34), (34 << 16) | 12)

    def test_pack_point_rejects_invalid_coordinates(self):
        with self.assertRaises(ValueError):
            pack_point(-1, 2)

    def test_background_click_requires_unique_target_title(self):
        result = click_window_background("", 10, 10)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_target")


if __name__ == "__main__":
    unittest.main()
