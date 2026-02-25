import subprocess
from pathlib import Path
from app.core.nexus import NexusComponent


class PyinstallerBuilder(NexusComponent):
    """
    Worker responsável por gerar o instalador do Jarvis.
    """

    def configure(self, config: dict | None = None):
        self.config = config or {}

    def can_execute(self, context: dict) -> bool:
        # Garante execução só em Windows
        return context["env"].get("RUNNER_OS", "").lower() == "windows"

    def execute(self, context: dict):
        root = Path(context["env"]["GITHUB_WORKSPACE"])

        build_script = root / "build_config.py"
        if not build_script.exists():
            raise FileNotFoundError("build_config.py not found at project root")

        subprocess.check_call(
            ["python", str(build_script)],
            cwd=root,
            shell=True,
        )

        return {
            "artifact": "dist/Jarvis_Installer.exe"
        }