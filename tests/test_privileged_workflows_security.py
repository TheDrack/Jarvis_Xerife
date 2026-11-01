"""Security contracts for manually dispatched repository mutation workflows."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / ".github" / "workflows" / "migrate_to_nexus_di.yml"
LIFECYCLE = ROOT / ".github" / "workflows" / "repo_lifecycle.yml"


def _load(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _checkout_steps(job):
    return [
        step
        for step in job.get("steps", [])
        if step.get("uses", "").startswith("actions/checkout@")
    ]


def test_migration_workflow_is_main_only_read_only_and_uses_trusted_checkout():
    workflow = _load(MIGRATION)
    job = workflow["jobs"]["migrate"]
    checkouts = _checkout_steps(job)

    assert workflow["permissions"] == {"contents": "read"}
    assert job["permissions"] == {"contents": "read"}
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert len(checkouts) == 1
    assert checkouts[0]["with"]["ref"] == "main"
    assert checkouts[0]["with"]["persist-credentials"] == "false"
    assert "token" not in checkouts[0]["with"]


def test_migration_workflow_is_preview_only_and_never_writes_to_git():
    workflow = _load(MIGRATION)
    job = workflow["jobs"]["migrate"]
    serialized = str(job)

    migration_step = next(
        step for step in job["steps"]
        if step.get("name") == "Run Nexus DI migration preview"
    )

    assert "scripts/migrate_to_nexus_di.py --dry-run" in migration_step["run"]
    assert "--apply" not in serialized
    assert "git push" not in serialized
    assert "git commit" not in serialized
    assert "GITHUB_TOKEN" not in serialized
    assert "secrets." not in serialized


def test_migration_workflow_publishes_a_reviewable_report_without_write_token():
    workflow = _load(MIGRATION)
    job = workflow["jobs"]["migrate"]
    upload = next(
        step for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )

    assert "nexus_di_migration_report.txt" in upload["with"]["path"]
    assert "migrate_nexus_di.log" in upload["with"]["path"]
    assert "GITHUB_TOKEN" not in str(job)


def test_lifecycle_workflow_is_main_only_read_only_and_uses_trusted_checkout():
    workflow = _load(LIFECYCLE)
    job = workflow["jobs"]["governance"]
    checkouts = _checkout_steps(job)

    assert workflow["permissions"] == {"contents": "read"}
    assert job["permissions"] == {"contents": "read"}
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert len(checkouts) == 1
    assert checkouts[0]["with"]["ref"] == "main"
    assert checkouts[0]["with"]["persist-credentials"] == "false"
    assert "token" not in checkouts[0]["with"]


def test_lifecycle_workflow_exports_a_patch_and_never_commits_or_pushes():
    workflow = _load(LIFECYCLE)
    job = workflow["jobs"]["governance"]
    serialized = str(job)
    execution = next(
        step for step in job["steps"]
        if step.get("name") == "Run lifecycle governance in isolated runner checkout"
    )
    upload = next(
        step for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )

    assert "repo_lifecycle_governance.py" in execution["run"]
    assert "git diff --binary" in execution["run"]
    assert "repo_lifecycle_governance.patch" in upload["with"]["path"]
    assert "git commit" not in serialized
    assert "git push" not in serialized
    assert "GITHUB_TOKEN" not in serialized
    assert "secrets." not in serialized
