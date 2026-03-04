# SECURITY GUARDRAILS – JARVIS

This document defines the mandatory security rules for the JARVIS project.
All contributors and automated workflows MUST follow these guardrails.

---

## 1. Capability Execution

- **Every capability execution MUST pass through `CapabilityAuthorizer`.**
- No component may call an executor directly without prior authorization.
- The mandatory execution flow is:
  ```
  AssistantService → CapabilityAuthorizer → Executor
  ```
- Capabilities not in the allowlist are rejected at the authorizer.

## 2. Sensitive Capabilities Require Human Confirmation

The following capabilities are classified as **sensitive** and require
`human_confirmed: true` in the execution payload:

- `system_executor`
- `auto_evolution`
- `github_worker`
- `pyinstaller_builder`
- `drive_uploader`
- `gist_uploader`

## 3. Payload Injection Protection

- All capability payloads are scanned for shell injection patterns before execution.
- Patterns blocked include: `;`, `|`, `` ` ``, `$()`, `../`, `eval`, `exec`,
  `system`, `subprocess`, `rm -rf`, `chmod`, `sudo`.

## 4. Secrets Management

- **No module may use `os.environ` directly for secret retrieval.**
- All secrets MUST be accessed via the `SecretsProvider` port
  (`app/ports/secrets_provider.py`).
- The only authorised `os.environ` reader is `EnvSecretsProvider`
  (`app/adapters/infrastructure/secrets/env_secrets_provider.py`).
- Secrets must never appear in logs, stack traces, or error messages.

## 5. PII / Privacy Protection

- **No raw PII may be stored in the vector index (FAISS).**
- All text MUST pass through `PiiRedactor.sanitize()` before embedding or indexing.
- The mandatory indexing flow is:
  ```
  Input → PiiRedactor → Embedding → FAISS
  ```
- PII categories currently redacted: email, CPF, phone number.
- Data purge methods `purge_by_user(user_id)` and `purge_all()` must remain
  functional and tested.

## 6. Vision / Image Upload

- External image uploads are **disabled by default**
  (`allow_external_vision = False`).
- Both `allow_external_vision == True` **AND** `user_consent == True` are
  required before any image is transmitted to an external API.
- Every upload attempt (whether allowed or blocked) MUST be written to the
  audit log with: timestamp, image source, and allow/block decision.
- **Image bytes must never be stored in logs.**

## 7. Auto-Evolution & Code Modification

- Automated workflows **must not** auto-merge changes to:
  - `capabilities/`
  - `app/adapters/infrastructure/` (execution-related files)
  - `app/application/security/`
- All modifications to capability files require human review.
- Security tests (`tests/security/`) are mandatory for any PR touching
  capability execution paths.

## 8. Test Requirements

- Every security-related component MUST have dedicated tests.
- Security tests live in `tests/security/`, `tests/privacy/`, and `tests/vision/`.
- All security tests must pass before merging any PR.
- Removing or skipping security tests is not permitted without explicit approval.

---

_Last updated: 2026-03-04_
