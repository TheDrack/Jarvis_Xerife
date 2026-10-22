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
            patch.object(status, "OVERLAY_ACK_FILE", self.root / "agent_overlay_ack.json"),
            patch.object(status, "ensure_overlay_started", return_value=True),
            patch.object(status, "_wait_for_overlay_ack", return_value=True),
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

    def test_begin_action_waits_for_overlay_ack_before_returning(self):
        with patch.object(status, "_wait_for_overlay_ack", return_value=True) as wait_for_ack:
            status.begin_action("observe screen")
        wait_for_ack.assert_called_once()
        args = wait_for_ack.call_args.args
        self.assertTrue(args[0])
        self.assertEqual(args[1], status.OVERLAY_ACK_TIMEOUT_SECONDS)

    def test_overlay_ack_is_bound_to_request_id(self):
        status._ack_overlay_visible("request-123")
        ack = json.loads((self.root / "agent_overlay_ack.json").read_text(encoding="utf-8"))
        self.assertEqual(ack["request_id"], "request-123")
        self.assertTrue(ack["visible"])

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


if __name__ == "__main__":
    unittest.main()
