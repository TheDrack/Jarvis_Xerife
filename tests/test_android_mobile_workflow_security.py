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


def test_android_workflow_defaults_to_read_only_and_scopes_write_to_publisher():
    workflow = _workflow()
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["assemble-debug"]["permissions"] == {"contents": "read"}
    assert jobs["build-release"]["permissions"] == {"contents": "read"}
    assert jobs["publish-release"]["permissions"] == {"contents": "write"}


def test_debug_build_is_read_only_and_does_not_receive_secrets():
    workflow = _workflow()
    debug_job = workflow["jobs"]["assemble-debug"]
    checkout = _checkout_step(debug_job)

    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert "secrets." not in str(debug_job)
    assert "GH_TOKEN" not in str(debug_job)


def test_release_build_is_restricted_to_main_and_has_no_write_permission():
    workflow = _workflow()
    release_job = workflow["jobs"]["build-release"]

    condition = release_job["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert condition.count("github.ref == 'refs/heads/main'") == 2
    assert release_job["permissions"] == {"contents": "read"}
    assert release_job["needs"] == "assemble-debug"


def test_release_build_checkout_does_not_persist_git_credentials():
    workflow = _workflow()
    checkout = _checkout_step(workflow["jobs"]["build-release"])

    assert checkout["with"]["persist-credentials"] == "false"
    assert checkout["with"]["ref"] == "${{ github.sha }}"


def test_publisher_only_downloads_artifact_and_uses_scoped_write_token():
    workflow = _workflow()
    publisher = workflow["jobs"]["publish-release"]

    assert publisher["needs"] == "build-release"
    assert publisher["permissions"] == {"contents": "write"}
    assert not any(step.get("uses", "").startswith("actions/checkout@") for step in publisher["steps"])
    publish_step = next(
        step for step in publisher["steps"] if step.get("name") == "Publish release APK"
    )
    assert publish_step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "secrets." not in str(publisher["steps"])
    assert "gradle " not in str(publisher["steps"])


def test_signing_secrets_are_confined_to_trusted_release_build():
    workflow = _workflow()
    debug_job = workflow["jobs"]["assemble-debug"]
    release_job = workflow["jobs"]["build-release"]
    publisher = workflow["jobs"]["publish-release"]

    assert "ANDROID_KEYSTORE_BASE64" not in str(debug_job)
    assert "ANDROID_KEYSTORE_PASSWORD" not in str(debug_job)
    assert "ANDROID_KEYSTORE_BASE64" in str(release_job)
    assert "ANDROID_KEYSTORE_PASSWORD" in str(release_job)
    assert "ANDROID_KEYSTORE_BASE64" not in str(publisher)


def test_pull_request_still_runs_the_debug_build():
    workflow = _workflow()

    assert "pull_request" in workflow["on"]
    assert "mobile/android/**" in str(workflow["on"]["pull_request"])
