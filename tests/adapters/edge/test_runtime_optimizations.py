import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.adapters.edge import jarvis_agent_status as status
from app.adapters.edge.visual_navigation_adapter import VisualNavigationAdapter


class RuntimeOptimizationTests(unittest.TestCase):
    def test_status_writer_uses_atomic_json_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.object(status, "STATUS_DIR", root), patch.object(status, "STATUS_FILE", root / "agent_activity.json"):
                status._write_status("working", "unit test")
                saved = json.loads((root / "agent_activity.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["phase"], "working")
                self.assertEqual(saved["action"], "unit test")
                self.assertEqual(list(root.glob("agent_activity_*.tmp")), [])

    def test_capture_retention_keeps_latest_count_and_current_capture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            files = []
            for index in range(5):
                path = root / f"jarvis_{index}.jpg"
                path.write_bytes(b"test")
                os.utime(path, (100 + index, 100 + index))
                files.append(path)
            adapter = VisualNavigationAdapter(template_dir=root / "templates", screenshot_dir=root)
            with patch.dict(os.environ, {"JARVIS_CAPTURE_RETENTION_COUNT": "3", "JARVIS_CAPTURE_MAX_AGE_DAYS": "0"}):
                adapter._prune_captures(files[-1])
            remaining = {item.name for item in root.glob("jarvis_*.jpg")}
            self.assertEqual(remaining, {"jarvis_2.jpg", "jarvis_3.jpg", "jarvis_4.jpg"})


if __name__ == "__main__":
    unittest.main()
