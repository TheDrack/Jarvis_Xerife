"""Regression tests for locating failed files from pytest JSON reports."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import jarvis_healer as healer
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


    def test_is_production_file_rejects_test_directories_and_pytest_names(self):
        test_paths = (
            "tests/helpers.py",
            "test/helpers.py",
            "tests/unit/test_sample.py",
            "src/sample_test.py",
            r"C:\\repo\\tests\\helpers.py",
            r"C:\\repo\\src\\sample_test.py",
        )
        for candidate in test_paths:
            with self.subTest(candidate=candidate):
                self.assertFalse(healer.is_production_file(Path(candidate)))

        self.assertTrue(healer.is_production_file(Path("app/services/worker.py")))

    def test_is_production_file_rejects_pytest_infrastructure_files(self):
        protected_paths = (
            "conftest.py",
            "app/conftest.py",
            "pytest.ini",
            "tox.ini",
            "setup.cfg",
            "pyproject.toml",
            ".coveragerc",
        )
        for candidate in protected_paths:
            with self.subTest(candidate=candidate):
                self.assertFalse(healer.is_production_file(Path(candidate)))

    def test_apply_fixes_refuses_to_modify_test_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            test_file = Path(temporary) / "tests" / "test_sample.py"
            test_file.parent.mkdir(parents=True)
            original = "def test_sample():\n    assert True\n"
            test_file.write_text(original, encoding="utf-8")

            result = healer.apply_fixes(
                test_file,
                [{
                    "action": "replace",
                    "old_code": "assert True",
                    "new_code": "assert False",
                }],
            )

            self.assertEqual(result, (0, 1))
            self.assertEqual(test_file.read_text(encoding="utf-8"), original)

    def test_apply_fixes_refuses_symlink_to_test_infrastructure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "tests" / "conftest.py"
            target.parent.mkdir(parents=True)
            original = "def pytest_configure(config):\n    pass\n"
            target.write_text(original, encoding="utf-8")
            link = root / "app" / "worker.py"
            link.parent.mkdir(parents=True)
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable on this runner: {exc}")

            result = healer.apply_fixes(
                link,
                [{
                    "action": "replace",
                    "old_code": "pass",
                    "new_code": "raise RuntimeError",
                }],
            )

            self.assertEqual(result, (0, 1))
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_heal_never_sends_conftest_from_traceback_to_llm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conftest = root / "conftest.py"
            conftest.write_text("def pytest_configure(config):\n    pass\n", encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({
                "summary": {"failed": 1, "error": 0},
                "tests": [],
            }), encoding="utf-8")
            log = root / "pytest.log"
            log.write_text(
                f'File "{conftest}", line 1, in pytest_configure\n',
                encoding="utf-8",
            )

            argv = [
                "jarvis_healer.py",
                "--report",
                str(report),
                "--log",
                str(log),
            ]
            with patch.object(healer, "REPO_ROOT", root):
                with patch.object(healer.sys, "argv", argv):
                    with patch.object(healer, "call_groq_healer") as model:
                        result = healer.heal()

            self.assertEqual(result, 1)
            model.assert_not_called()

    def test_heal_never_sends_failed_test_file_to_llm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test_file = root / "tests" / "unit" / "test_sample.py"
            test_file.parent.mkdir(parents=True)
            original = "def test_sample():\n    assert True\n"
            test_file.write_text(original, encoding="utf-8")
            report = root / "report.json"
            report.write_text(json.dumps({
                "summary": {"failed": 1, "error": 0},
                "tests": [{
                    "nodeid": "tests/unit/test_sample.py::test_sample",
                    "outcome": "failed",
                    "call": {"crash": {"message": "AssertionError: regression"}},
                }],
            }), encoding="utf-8")
            log = root / "pytest.log"
            log.write_text("", encoding="utf-8")

            argv = [
                "jarvis_healer.py",
                "--report",
                str(report),
                "--log",
                str(log),
            ]
            with patch.object(healer, "REPO_ROOT", root):
                with patch.object(healer.sys, "argv", argv):
                    with patch.object(healer, "call_groq_healer") as model:
                        result = healer.heal()

            self.assertEqual(result, 1)
            model.assert_not_called()
            self.assertEqual(test_file.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
