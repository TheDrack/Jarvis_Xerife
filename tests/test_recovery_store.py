"""Tests for conservative local recovery checkpoints."""
import tempfile
import unittest
from pathlib import Path
from app.core.recovery_store import RecoveryError, RecoveryStore

class RecoveryStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "workspace"
        self.root.mkdir()
        self.store = RecoveryStore(self.root, Path(temp.name) / "recovery")

    def test_restores_original_binary_bytes(self):
        target = self.root / "settings.bin"
        target.write_bytes(b"\x00before\xff")
        cp = self.store.checkpoint(["settings.bin"], reason="test mutation", run_id="run-1")
        target.write_bytes(b"after")
        self.store.seal(cp["checkpoint_id"])
        result = self.store.restore(cp["checkpoint_id"])
        self.assertTrue(result["success"])
        self.assertEqual(target.read_bytes(), b"\x00before\xff")
        self.assertTrue(self.store.verify_journal()["valid"])

    def test_refuses_to_overwrite_post_seal_changes(self):
        target = self.root / "settings.txt"
        target.write_text("before", encoding="utf-8")
        cp = self.store.checkpoint(["settings.txt"], reason="conflict test")
        target.write_text("operation result", encoding="utf-8")
        self.store.seal(cp["checkpoint_id"])
        target.write_text("unrelated later change", encoding="utf-8")
        result = self.store.restore(cp["checkpoint_id"])
        self.assertFalse(result["success"])
        self.assertEqual(result["results"][0]["status"], "conflict")
        self.assertEqual(target.read_text(encoding="utf-8"), "unrelated later change")

    def test_never_deletes_new_files_without_authorization(self):
        cp = self.store.checkpoint(["created.txt"], reason="new file test")
        target = self.root / "created.txt"
        target.write_text("created by operation", encoding="utf-8")
        self.store.seal(cp["checkpoint_id"])
        result = self.store.restore(cp["checkpoint_id"])
        self.assertFalse(result["success"])
        self.assertEqual(result["results"][0]["status"], "requires_authorization")
        self.assertTrue(target.exists())

    def test_restores_file_deleted_by_operation(self):
        target = self.root / "important.txt"
        target.write_text("recover me", encoding="utf-8")
        cp = self.store.checkpoint(["important.txt"], reason="deleted file test")
        target.unlink()
        self.store.seal(cp["checkpoint_id"])
        result = self.store.restore(cp["checkpoint_id"])
        self.assertTrue(result["success"])
        self.assertEqual(target.read_text(encoding="utf-8"), "recover me")

    def test_rejects_path_escape(self):
        with self.assertRaises(RecoveryError):
            self.store.checkpoint(["../outside.txt"], reason="escape test")

    def test_journal_detects_tampering(self):
        cp = self.store.checkpoint(["missing.txt"], reason="tamper test")
        self.store.seal(cp["checkpoint_id"])
        journal = self.store.journal_path
        journal.write_text(journal.read_text(encoding="utf-8").replace("checkpoint_created", "checkpoint_changed", 1), encoding="utf-8")
        self.assertFalse(self.store.verify_journal()["valid"])

if __name__ == "__main__":
    unittest.main()
