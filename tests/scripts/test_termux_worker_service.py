import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_RUN = ROOT / "deploy" / "termux" / "runit" / "jarvis-agent-worker" / "run"
WORKER_ENV = ROOT / "deploy" / "termux" / "worker.env.example"
CONTROL = ROOT / "scripts" / "jarvis-worker"
INSTALLER = ROOT / "scripts" / "install_termux_worker_service.sh"


def _find_bash_executable():
    if os.name == "nt":
        program_files = (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramW6432", r"C:\Program Files"),
        )
        for root in program_files:
            for relative in (Path("Git") / "bin" / "bash.exe", Path("Git") / "usr" / "bin" / "bash.exe"):
                candidate = Path(root) / relative
                if candidate.is_file():
                    return str(candidate)
    candidate = shutil.which("bash")
    if candidate and "system32" not in candidate.lower():
        return candidate
    return None


BASH = _find_bash_executable()


def _bash_path(path):
    value = str(path)
    if os.name != "nt":
        return value
    drive, tail = os.path.splitdrive(value)
    normalized_tail = tail.replace("\\", "/")
    return f"/{drive.rstrip(':').lower()}{normalized_tail}"


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


@unittest.skipUnless(BASH, "requires Bash (Git Bash on Windows)")
class TermuxWorkerAutostartTests(unittest.TestCase):
    def _run_control(self, command, *, initially_down, worker_count=1):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            prefix = root / "prefix"
            service = prefix / "var" / "service" / "jarvis-agent-worker"
            config = home / ".config" / "jarvis" / "agent-worker" / "worker.env"
            fake_bin = prefix / "bin"
            service.mkdir(parents=True)
            config.parent.mkdir(parents=True)
            fake_bin.mkdir(parents=True)
            if initially_down:
                (service / "down").touch()
            if worker_count == 1:
                config_text = (
                    "JARVIS_MINI_AGENT_ENABLED=true\n"
                    "JARVIS_MINI_AGENT_WORKERS=1\n"
                    "JARVIS_AGENT_ID=jarvis-termux-mini-1\n"
                    "JARVIS_AGENT_REMOTE_INFERENCE=true\n"
                    "JARVIS_TASK_QUEUE_API_URL=https://jarvis.example\n"
                    "JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_TERMUX_MINI_1=worker-token\n"
                )
            else:
                config_text = (
                    "JARVIS_MINI_AGENT_ENABLED=true\n"
                    f"JARVIS_MINI_AGENT_WORKERS={worker_count}\n"
                    "JARVIS_AGENT_ID=jarvis-mobile\n"
                    "JARVIS_TASK_QUEUE_API_URL=https://jarvis.example\n"
                    "JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_MOBILE_1=token-one\n"
                    "JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_MOBILE_2=token-two\n"
                    "JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_MOBILE_1=false\n"
                    "JARVIS_AGENT_MODEL_PROVIDER_JARVIS_MOBILE_1=gemini\n"
                    "FREELLMAPI_API_KEY_JARVIS_MOBILE_1=gemini-key\n"
                    "FREELLMAPI_BASE_URL_JARVIS_MOBILE_1=https://generativelanguage.googleapis.com/v1beta\n"
                    "FREELLMAPI_MODEL_JARVIS_MOBILE_1=gemini-model\n"
                    "JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_MOBILE_2=false\n"
                    "JARVIS_AGENT_MODEL_PROVIDER_JARVIS_MOBILE_2=xai\n"
                    "FREELLMAPI_API_KEY_JARVIS_MOBILE_2=xai-key\n"
                    "FREELLMAPI_BASE_URL_JARVIS_MOBILE_2=https://api.x.ai/v1\n"
                    "FREELLMAPI_MODEL_JARVIS_MOBILE_2=grok-model\n"
                )
            config.write_text(config_text, encoding="utf-8")
            marker = root / "marker-state"
            fake_sv = fake_bin / "sv"
            fake_sv.write_text(
                "#!/bin/sh\n"
                "command=$1\n"
                f"if [ -e '{_bash_path(service)}/down' ]; then state=down; else state=up; fi\n"
                f"printf '%s:%s\n' \"$command\" \"$state\" >> '{_bash_path(marker)}'\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_sv.chmod(0o755)
            env = dict(os.environ)
            env.update({"HOME": _bash_path(home), "PREFIX": _bash_path(prefix)})
            result = subprocess.run(
                [BASH, _bash_path(CONTROL), command],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return marker.read_text(encoding="utf-8").splitlines(), (service / "down").exists()

    def test_start_clears_down_marker_before_bringing_worker_up(self):
        calls, down_exists = self._run_control("start", initially_down=True)
        self.assertEqual(calls[0], "up:up")
        self.assertFalse(down_exists)

    def test_stop_persists_down_marker_before_stopping_worker(self):
        calls, down_exists = self._run_control("stop", initially_down=False)
        self.assertEqual(calls[0], "down:down")
        self.assertTrue(down_exists)

    def test_boot_start_clears_down_marker_when_configuration_is_valid(self):
        calls, down_exists = self._run_control("boot-start", initially_down=True)
        self.assertEqual(calls[0], "up:up")
        self.assertFalse(down_exists)

    def test_start_accepts_distinct_provider_configurations_for_multiple_agents(self):
        calls, down_exists = self._run_control(
            "start", initially_down=True, worker_count=2
        )
        self.assertEqual(calls[0], "up:up")
        self.assertFalse(down_exists)

    def test_runit_worker_process_receives_multiple_per_agent_provider_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            prefix = root / "prefix"
            repo = home / "Jarvis_Xerife_repo"
            config = root / "worker.env"
            fake_bin = prefix / "bin"
            repo.mkdir(parents=True)
            fake_bin.mkdir(parents=True)
            config.write_text(
                "JARVIS_MINI_AGENT_ENABLED=true\n"
                "JARVIS_MINI_AGENT_WORKERS=2\n"
                "JARVIS_AGENT_ID=jarvis-mobile\n"
                "JARVIS_TASK_QUEUE_API_URL=https://jarvis.example\n"
                "JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_MOBILE_1=token-one\n"
                "JARVIS_TASK_QUEUE_WORKER_TOKEN_JARVIS_MOBILE_2=token-two\n"
                "JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_MOBILE_1=false\n"
                "JARVIS_AGENT_MODEL_PROVIDER_JARVIS_MOBILE_1=gemini\n"
                "FREELLMAPI_API_KEY_JARVIS_MOBILE_1=gemini-key\n"
                "FREELLMAPI_BASE_URL_JARVIS_MOBILE_1=https://generativelanguage.googleapis.com/v1beta\n"
                "FREELLMAPI_MODEL_JARVIS_MOBILE_1=gemini-model\n"
                "JARVIS_AGENT_REMOTE_INFERENCE_JARVIS_MOBILE_2=false\n"
                "JARVIS_AGENT_MODEL_PROVIDER_JARVIS_MOBILE_2=xai\n"
                "FREELLMAPI_API_KEY_JARVIS_MOBILE_2=xai-key\n"
                "FREELLMAPI_BASE_URL_JARVIS_MOBILE_2=https://api.x.ai/v1\n"
                "FREELLMAPI_MODEL_JARVIS_MOBILE_2=grok-model\n",
                encoding="utf-8",
            )
            fake_python = fake_bin / "python"
            fake_python.write_text(
                "#!/bin/sh\n"
                "printf '%s|%s\\n' \"$JARVIS_MINI_AGENT_WORKERS\" \"$JARVIS_AGENT_ID\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env = dict(os.environ)
            env.update(
                {
                    "HOME": _bash_path(home),
                    "PREFIX": _bash_path(prefix),
                    "JARVIS_REPO_ROOT": _bash_path(repo),
                    "JARVIS_WORKER_ENV_FILE": _bash_path(config),
                }
            )
            result = subprocess.run(
                [BASH, _bash_path(SERVICE_RUN)],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("2|jarvis-mobile", result.stdout)
