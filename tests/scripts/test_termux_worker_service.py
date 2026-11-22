import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_RUN = ROOT / "deploy" / "termux" / "runit" / "jarvis-agent-worker" / "run"
WORKER_ENV = ROOT / "deploy" / "termux" / "worker.env.example"
CONTROL = ROOT / "scripts" / "jarvis-worker"
INSTALLER = ROOT / "scripts" / "install_termux_worker_service.sh"


class TermuxObjectivePersistenceWiringTests(unittest.TestCase):
    def test_service_enables_local_objective_journal_by_default(self):
        source = SERVICE_RUN.read_text(encoding="utf-8")
        self.assertIn(
            'export JARVIS_OBJECTIVE_JOURNAL_ENABLED="${JARVIS_OBJECTIVE_JOURNAL_ENABLED:-true}"',
            source,
        )
        self.assertIn("jarvis-mobile/state/agent-objectives.sqlite3", source)

    def test_example_configuration_documents_the_journal(self):
        source = WORKER_ENV.read_text(encoding="utf-8")
        self.assertIn("JARVIS_OBJECTIVE_JOURNAL_ENABLED=true", source)
        self.assertIn("JARVIS_OBJECTIVE_JOURNAL_PATH=", source)

    def test_control_script_persists_journal_configuration_and_exposes_status(self):
        source = CONTROL.read_text(encoding="utf-8")
        self.assertIn("JARVIS_OBJECTIVE_JOURNAL_ENABLED=true", source)
        self.assertIn("JARVIS_OBJECTIVE_JOURNAL_PATH", source)
        self.assertIn("app.multiagent.objective_journal", source)
        self.assertIn("objectives)", source)
        self.assertIn("prune-objectives)", source)

    def test_installer_ships_the_control_script(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("scripts/jarvis-worker", source)
        self.assertIn("worker_daemon.py", source)


if __name__ == "__main__":
    unittest.main()
