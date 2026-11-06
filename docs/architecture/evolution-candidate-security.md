# Evolution Candidate Security Boundary

## Purpose

Generated code is untrusted input. It must not execute in the host process that has access to provider credentials, the repository checkout, or GitHub publication credentials.

The evolution pipeline therefore has two separate trust domains:

1. **Candidate generation and validation** — receives only the model-provider credential. The candidate is applied to a disposable repository snapshot and tested inside the Docker sandbox.
2. **Trusted publication** — receives the validated artifact and GitHub publication credential. It verifies the artifact and writes the target file, but never imports, executes, or tests candidate code.

## Candidate validation job

The candidate job:

- checks out the trusted base revision with checkout credentials disabled;
- resolves an explicit `target_file` from trusted mission/capability metadata, never from model output;
- invokes the Gatekeeper, which enforces repository path policy and protected prefixes;
- creates a repository snapshot outside the host checkout and replaces only the target file in that snapshot;
- runs the complete test suite in `Dockerfile.evolution-sandbox`.

The container runs as a non-root UID with:

- `--network none`;
- no host bind mounts and no Docker socket;
- no provider, GitHub, Supabase, or Render secrets in its environment;
- a read-only container root with bounded writable tmpfs mounts;
- dropped Linux capabilities and no-new-privileges;
- memory, CPU, PID, and wall-clock limits.

The Docker image includes Git so the snapshot can receive a synthetic local commit for tests that inspect repository history. It has no remote and no credentials. A timeout attempts to force-remove the named container.

A temporary directory is **not** a security boundary. The temporary artifact directory only transports validated bytes between jobs. The Docker container is the execution boundary.

## Validated artifact contract

After Gatekeeper approval, the candidate job writes an artifact outside the checkout containing:

- `manifest.json`: schema version, mission ID, explicit target path, candidate filename, SHA-256, validation backend, sandbox image, and source commit;
- `candidate.py`: the exact candidate bytes that passed the Docker test run.

The artifact is uploaded only when the manifest exists. A mission without trusted `target_file` metadata is blocked before the LLM call; it does not guess a path or create an artifact.

## Trusted publication job

The publisher job has GitHub write credentials but no model-provider credential. It:

1. requires exactly one artifact manifest;
2. checks the schema, validation marker, Docker backend, image identity, candidate size, and SHA-256;
3. verifies the source commit still matches the checked-out default branch;
4. resolves the target through `repository_path_policy`, rejects traversal, symlinks, frozen directories, and protected prefixes;
5. requires a tracked, clean Python target file;
6. creates a feature branch and atomically writes only the validated target;
7. stages exactly that path, verifies the staged file list and `git diff --check`, then pushes and opens a PR.

The publisher does not execute candidate code. CI runs again against the resulting PR.

## Fail-closed conditions

No publication occurs when Docker is unavailable, candidate tests fail, the target is absent or protected, the artifact digest is wrong, the source commit is stale, the target has local changes, the target is untracked, or the publisher cannot prove that only the target file is staged.

## Current integration status

- The Docker-backed sandbox and adversarial integration test are wired into PR validation.
- The scheduled evolution workflow is split into candidate-validation and trusted-publication jobs.
- The current pending capability inventory does not yet provide trusted `target_file` metadata. Until that mapping is populated or a trusted target resolver is implemented, scheduled evolution intentionally reports a blocked/no-op result and does not invoke the LLM.
- `JarvisDevAgent` still needs to be routed through this same artifact contract before it can publish generated changes.
- Main branch protection is a repository-administration setting and is tracked separately.