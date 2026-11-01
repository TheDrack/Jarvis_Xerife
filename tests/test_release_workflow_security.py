"""Security contracts for the Windows installer release workflow."""
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _load_workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _steps(job):
    return job.get("steps", [])


def test_release_workflow_defaults_to_read_only_permissions():
    workflow = _load_workflow()

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["build-windows"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["publish-release"]["permissions"] == {"contents": "write"}


def test_installer_build_only_checks_out_the_selected_sha_without_persisting_credentials():
    workflow = _load_workflow()
    build = workflow["jobs"]["build-windows"]
    checkouts = [
        step for step in _steps(build)
        if step.get("uses", "").startswith("actions/checkout@")
    ]

    assert len(checkouts) == 1
    assert checkouts[0]["with"]["ref"] == "${{ github.sha }}"
    assert checkouts[0]["with"]["persist-credentials"] == "false"
    assert "secrets." not in str(build)


def test_build_is_limited_to_main_or_versioned_release_tags():
    workflow = _load_workflow()
    build = workflow["jobs"]["build-windows"]
    condition = build["if"]

    assert "github.event_name == 'workflow_dispatch'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert "startsWith(github.ref, 'refs/tags/v')" in condition


def test_release_tag_must_be_reachable_from_main():
    workflow = _load_workflow()
    build = workflow["jobs"]["build-windows"]
    verification = next(
        step for step in _steps(build)
        if step.get("name") == "Verify release tag belongs to main history"
    )

    assert "git fetch --no-tags origin" in verification["run"]
    assert "git merge-base --is-ancestor" in verification["run"]


def test_release_publication_is_separate_and_does_not_execute_project_code():
    workflow = _load_workflow()
    publish = workflow["jobs"]["publish-release"]

    assert publish["needs"] == "build-windows"
    assert "startsWith(github.ref, 'refs/tags/v')" in publish["if"]
    assert not any(
        step.get("uses", "").startswith("actions/checkout@")
        for step in _steps(publish)
    )
    assert any(
        step.get("uses", "").startswith("actions/download-artifact@")
        for step in _steps(publish)
    )
    assert "contents" not in str(publish.get("env", {}))
