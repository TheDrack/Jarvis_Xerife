import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.adapters.edge import jarvis_agent_status as status


class AgentStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [
            patch.object(status, "STATUS_DIR", self.root),
            patch.object(status, "STATUS_FILE", self.root / "agent_activity.json"),
            patch.object(status, "ensure_overlay_started", return_value=True),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_begin_and_end_publish_status(self):
        status.begin_action("test action")
        active = json.loads((self.root / "agent_activity.json").read_text(encoding="utf-8"))
        self.assertEqual(active["phase"], "working")
        self.assertEqual(active["action"], "test action")

        status.end_action("test action", True, "")
        done = json.loads((self.root / "agent_activity.json").read_text(encoding="utf-8"))
        self.assertEqual(done["phase"], "success")

    def test_tracked_action_marks_failure_result(self):
        @status.tracked_action("test failure")
        def operation():
            return {"success": False, "status": "not_found", "message": "target missing"}

        result = operation()
        saved = json.loads((self.root / "agent_activity.json").read_text(encoding="utf-8"))
        self.assertFalse(result["success"])
        self.assertEqual(saved["phase"], "attention")
        self.assertEqual(saved["message"], "target missing")

    def test_tracked_action_marks_exception_and_reraises(self):
        @status.tracked_action("test exception")
        def operation():
            raise RuntimeError("expected test error")

        with self.assertRaisesRegex(RuntimeError, "expected test error"):
            operation()
        saved = json.loads((self.root / "agent_activity.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["phase"], "attention")
        self.assertEqual(saved["message"], "expected test error")

    def test_overlay_ack_is_action_specific(self):
        payload = {"pid": 123, "updated_at": 10.5, "action_id": "action-1", "action": "open browser", "phase": "working"}
        status._publish_overlay_ready(payload)
        ready = json.loads((self.root / "agent_overlay_ready.json").read_text(encoding="utf-8"))
        self.assertEqual(ready["pid"], payload["pid"])
        self.assertEqual(ready["action_id"], payload["action_id"])
        self.assertEqual(ready["action"], payload["action"])
        self.assertTrue(ready["visible"])

    def test_overlay_ack_ignores_non_working_status(self):
        status._publish_overlay_ready({"phase": "success", "pid": 123, "updated_at": 10.5, "action": "done"})
        self.assertFalse((self.root / "agent_overlay_ready.json").exists())

    def test_wait_for_overlay_visible_matches_exact_action(self):
        payload = {"phase": "working", "pid": 123, "updated_at": 10.5, "action_id": "action-1", "action": "open browser"}
        status._publish_overlay_ready(payload)
        with patch.object(status.os, "name", "nt"):
            self.assertTrue(status._wait_for_overlay_visible(payload, timeout=0.1))
            stale = dict(payload, action_id="action-2")
            self.assertFalse(status._wait_for_overlay_visible(stale, timeout=0.0))

    def test_begin_action_waits_for_overlay_ack_on_windows(self):
        # Simulate the Windows branch without changing os.name during file I/O:
        # patching os.name globally makes pathlib choose WindowsPath on Linux and
        # causes the status lock to import the unavailable msvcrt module.
        payload = {
            "pid": 123,
            "updated_at": 10.5,
            "action_id": "action-1",
            "action": "windows action",
            "phase": "working",
        }
        with patch.object(status, "_write_status", return_value=payload), \
             patch.object(status.os, "name", "nt"), \
             patch.object(status, "_wait_for_overlay_visible") as wait:
            status.begin_action("windows action")
        wait.assert_called_once_with(payload)

    def test_non_windows_begin_action_does_not_wait_for_overlay(self):
        payload = {"phase": "working", "action": "portable action", "updated_at": 1.0, "pid": 123}
        with patch.object(status.os, "name", "posix"), \
             patch.object(status, "_write_status", return_value=payload), \
             patch.object(status, "ensure_overlay_started", return_value=True), \
             patch.object(status, "_wait_for_overlay_visible") as wait:
            status.begin_action("portable action")
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
