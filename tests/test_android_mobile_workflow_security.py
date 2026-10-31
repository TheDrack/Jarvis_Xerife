"""Security contract tests for the Android build workflow."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "android-mobile-build.yml"


def _workflow():
    return yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _checkout_step(job):
    return next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )


def test_android_workflow_defaults_to_read_only_and_scopes_release_write():
    workflow = _workflow()
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["assemble-debug"]["permissions"] == {"contents": "read"}
    assert jobs["publish-release"]["permissions"] == {"contents": "write"}


def test_debug_build_does_not_persist_credentials_or_receive_secrets():
    workflow = _workflow()
    debug_job = workflow["jobs"]["assemble-debug"]
    checkout = _checkout_step(debug_job)

    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert "secrets." not in str(debug_job)
    assert "GH_TOKEN" not in str(debug_job)


def test_release_job_is_limited_to_trusted_main_events():
    workflow = _workflow()
    release_job = workflow["jobs"]["publish-release"]

    condition = release_job["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert condition.count("github.ref == 'refs/heads/main'") == 2
    assert release_job["needs"] == "assemble-debug"


def test_release_checkout_does_not_leave_git_credentials_in_workspace():
    workflow = _workflow()
    checkout = _checkout_step(workflow["jobs"]["publish-release"])

    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["with"]["ref"] == "${{ github.sha }}"


def test_signing_secrets_and_write_token_are_confined_to_release_job():
    workflow = _workflow()
    debug_job = workflow["jobs"]["assemble-debug"]
    release_job = workflow["jobs"]["publish-release"]

    assert "ANDROID_KEYSTORE_BASE64" not in str(debug_job)
    assert "ANDROID_KEYSTORE_PASSWORD" not in str(debug_job)
    assert "GH_TOKEN" not in str(debug_job)

    release_steps = str(release_job["steps"])
    assert "secrets.ANDROID_KEYSTORE_BASE64" in release_steps
    assert "secrets.ANDROID_KEYSTORE_PASSWORD" in release_steps
    assert "GH_TOKEN: ${{ github.token }}" in release_steps
