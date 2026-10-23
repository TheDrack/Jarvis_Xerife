"""Regression tests for locating failed files from pytest JSON reports."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.jarvis_healer import extract_failed_files_from_report


class ExtractFailedFilesFromReportTests(unittest.TestCase):
    def test_resolves_failed_nodeid_and_includes_failure_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test_file = root / "tests" / "unit" / "test_sample.py"
            test_file.parent.mkdir(parents=True)
            test_file.write_text("def test_sample(): pass\n", encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({
                "summary": {"failed": 1, "error": 0},
                "tests": [{
                    "nodeid": "tests/unit/test_sample.py::test_sample",
                    "outcome": "failed",
                    "call": {"crash": {"message": "AssertionError: expected true"}},
                }],
            }), encoding="utf-8")

            files, context = extract_failed_files_from_report(report, root)

            self.assertEqual(files, [test_file.resolve()])
            self.assertIn("test_sample.py::test_sample", context)
            self.assertIn("AssertionError", context)

    def test_ignores_paths_outside_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            root.mkdir()
            outside = Path(temporary) / "outside.py"
            outside.write_text("pass\n", encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({
                "tests": [{
                    "nodeid": "../outside.py::test_outside",
                    "outcome": "failed",
                    "call": {"crash": {"message": "failure"}},
                }],
            }), encoding="utf-8")

            files, context = extract_failed_files_from_report(report, root)

            self.assertEqual(files, [])
            self.assertIn("test_outside", context)

    def test_ignores_passed_tests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test_file = root / "test_sample.py"
            test_file.write_text("pass\n", encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({
                "tests": [{"nodeid": "test_sample.py::test_sample", "outcome": "passed"}],
            }), encoding="utf-8")

            files, context = extract_failed_files_from_report(report, root)

            self.assertEqual(files, [])
            self.assertEqual(context, "")


if __name__ == "__main__":
    unittest.main()
