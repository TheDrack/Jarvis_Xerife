import os
import subprocess
import sys
from pathlib import Path


def test_evolution_batch_script_requires_explicit_opt_in():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("EVOLUTION_ENABLED", None)
    # The CI runner may use a Windows legacy console encoding; force deterministic capture.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "evolve_all_pending.py"), "--legacy-capability", "--cap-id", "CAP-001"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 2
    output = (result.stdout or "") + (result.stderr or "")
    # The parent process must decode the child UTF-8 stream explicitly on Windows.
    assert "Autoevolução pausada:" in output or "EVOLUTION_PAUSED" in output
