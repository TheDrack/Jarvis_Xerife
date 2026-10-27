"""Regression tests for the hourly audit's pytest configuration."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_hourly_audit_installs_pytest_coverage_plugin():
    """pytest.ini uses --cov options, so the scheduled job must install pytest-cov."""
    pytest_config = (PROJECT_ROOT / "pytest.ini").read_text(encoding="utf-8")
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "hourly_curiosity_audit.yml"
    ).read_text(encoding="utf-8")

    assert "--cov=" in pytest_config
    assert "pytest-cov" in workflow, (
        "Hourly audit installs pytest but not pytest-cov; pytest.ini uses "
        "--cov options, so the suite exits before collecting tests."
    )
