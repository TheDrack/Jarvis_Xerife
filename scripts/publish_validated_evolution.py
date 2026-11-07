"""Publish a previously validated evolution artifact without executing it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from app.application.security.repository_path_policy import (  # noqa: E402
    UnsafeRepositoryPath,
    contains_frozen_directory,
    protected_prefix_for,
    resolve_repository_path,
)  # noqa: E402

MAX_CANDIDATE_BYTES = 2 * 1024 * 1024


class PublicationError(RuntimeError):
    """A validated artifact failed a trusted publication check."""


def _run(command: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise PublicationError(
            f"command_failed:{command[0]}:exit={result.returncode}:{detail[:1000]}"
        )
    return result


def _atomic_write(target: Path, content: bytes) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _load_artifact(artifact_dir: Path) -> tuple[Dict[str, Any], bytes]:
    manifests = sorted(artifact_dir.glob("*/manifest.json"))
    if len(manifests) != 1:
        raise PublicationError(
            f"expected_exactly_one_manifest_found_{len(manifests)}"
        )

    manifest_path = manifests[0]
    if manifest_path.is_symlink():
        raise PublicationError("manifest_symlink_forbidden")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise PublicationError("unsupported_manifest_schema")
    if manifest.get("validated") is not True:
        raise PublicationError("candidate_not_validated")
    if manifest.get("validation_backend") != "docker":
        raise PublicationError("docker_validation_required")
    if not str(manifest.get("sandbox_image", "")).strip():
        raise PublicationError("sandbox_image_missing")

    if manifest.get("candidate_file") != "candidate.py":
        raise PublicationError("unexpected_candidate_filename")

    candidate_path = manifest_path.parent / "candidate.py"
    if candidate_path.is_symlink() or not candidate_path.is_file():
        raise PublicationError("candidate_file_missing_or_symlink")

    payload = candidate_path.read_bytes()
    if not payload or len(payload) > MAX_CANDIDATE_BYTES:
        raise PublicationError("candidate_size_invalid")

    digest = hashlib.sha256(payload).hexdigest()
    if digest != manifest.get("sha256"):
        raise PublicationError("candidate_digest_mismatch")

    if not isinstance(manifest.get("mission_id"), str) or not manifest["mission_id"].strip():
        raise PublicationError("mission_id_missing")
    if not isinstance(manifest.get("target_file"), str) or not manifest["target_file"].strip():
        raise PublicationError("target_file_missing")

    return manifest, payload


def publish_artifact(artifact_dir: Path, repository_root: Path) -> Dict[str, str]:
    if not os.getenv("GH_TOKEN"):
        raise PublicationError("GH_TOKEN_required_in_trusted_publisher_job")

    root = repository_root.resolve()
    artifact_root = artifact_dir.resolve()
    if artifact_root == root or root in artifact_root.parents:
        raise PublicationError("artifact_directory_must_be_outside_repository")
    manifest, payload = _load_artifact(artifact_root)
    expected_image = os.getenv("EXPECTED_EVOLUTION_SANDBOX_IMAGE", "").strip()
    if not expected_image:
        raise PublicationError("expected_sandbox_image_required")
    if manifest["sandbox_image"] != expected_image:
        raise PublicationError("sandbox_image_mismatch")

    try:
        target_path, normalized_target, _ = resolve_repository_path(
            root, manifest["target_file"], reject_symlinks=True
        )
    except (UnsafeRepositoryPath, OSError, RuntimeError) as exc:
        raise PublicationError(f"unsafe_target_path:{exc}") from exc

    if target_path.suffix.casefold() != ".py" or not target_path.is_file():
        raise PublicationError("target_must_be_existing_python_file")
    if protected_prefix_for(normalized_target) or contains_frozen_directory(normalized_target):
        raise PublicationError("target_path_is_protected")

    current_branch = _run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], root
    ).stdout.strip()
    if current_branch not in {"main", "master"}:
        raise PublicationError(f"publisher_must_start_from_default_branch:{current_branch}")

    current_commit = _run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    if current_commit != manifest.get("source_commit"):
        raise PublicationError("source_commit_mismatch_stale_candidate_artifact")

    staged = _run(["git", "diff", "--cached", "--quiet"], root, check=False)
    if staged.returncode != 0:
        raise PublicationError("pre_staged_changes_detected")

    status = _run(
        ["git", "status", "--porcelain", "--", normalized_target],
        root,
        check=False,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise PublicationError("target_has_local_changes")

    tracked = _run(
        ["git", "ls-files", "--error-unmatch", normalized_target],
        root,
        check=False,
    )
    if tracked.returncode != 0:
        raise PublicationError("target_must_be_tracked")

    mission_slug = re.sub(
        r"[^A-Za-z0-9._-]+", "-", manifest["mission_id"]
    ).strip("-")[:48] or "mission"
    digest = manifest["sha256"]
    branch = f"auto-evolution/{mission_slug}-{digest[:8]}"
    title = f"[JARVIS Evolution] {manifest['mission_id']}"
    body = (
        "This candidate was validated in the isolated Docker sandbox before publication.\n\n"
        f"- Mission: `{manifest['mission_id']}`\n"
        f"- Target: `{normalized_target}`\n"
        f"- Sandbox image: `{manifest['sandbox_image']}`\n"
        f"- Candidate SHA-256: `{digest}`\n\n"
        "The publisher job only verifies the artifact and writes the validated file; "
        "it does not execute candidate code."
    )

    existing_prs_result = _run(
        [
            "gh", "pr", "list",
            "--state", "all",
            "--search", f"in:title {manifest['mission_id']}",
            "--json", "number,title,state",
            "--limit", "100",
        ],
        root,
    )
    try:
        existing_prs = json.loads(existing_prs_result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise PublicationError("existing_mission_pr_query_invalid") from exc
    if not isinstance(existing_prs, list):
        raise PublicationError("existing_mission_pr_query_invalid")
    duplicate = next(
        (item for item in existing_prs if item.get("title") == title),
        None,
    )
    if duplicate:
        raise PublicationError(
            "mission_pr_already_exists:"
            f"{duplicate.get('number', 'unknown')}:"
            f"{duplicate.get('state', 'unknown')}"
        )

    _run(["gh", "auth", "setup-git"], root)
    _run(["git", "checkout", "-b", branch], root)
    _atomic_write(target_path, payload)

    _run(["git", "add", "--", normalized_target], root)
    staged_names = _run(
        ["git", "diff", "--cached", "--name-only"], root
    ).stdout.splitlines()
    if not staged_names or {
        name.replace("\\", "/") for name in staged_names
    } != {normalized_target}:
        raise PublicationError("staged_diff_must_contain_only_target_file")

    _run(["git", "diff", "--cached", "--check"], root)
    _run(["git", "config", "user.name", "Jarvis-Bot"], root)
    _run(["git", "config", "user.email", "jarvis@bot.com"], root)
    _run(["git", "commit", "-m", title], root)
    _run(["git", "push", "--set-upstream", "origin", branch], root)

    pr = _run(
        [
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--head", branch,
            "--base", "main",
        ],
        root,
    )
    pr_url = pr.stdout.strip()
    pr_number = pr_url.rstrip("/").split("/")[-1]
    if not pr_number.isdigit():
        raise PublicationError("unable_to_parse_pull_request_number")

    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"pr_number={pr_number}\n")
            output.write(f"branch={branch}\n")
            output.write(f"pr_url={pr_url}\n")

    return {"pr_number": pr_number, "branch": branch, "pr_url": pr_url}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a validated evolution artifact without executing it"
    )
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args()

    try:
        result = publish_artifact(Path(args.artifact_dir), _ROOT)
    except (PublicationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"❌ Publication rejected: {exc}", file=sys.stderr)
        return 1

    print(f"✅ Pull request created: {result['pr_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
