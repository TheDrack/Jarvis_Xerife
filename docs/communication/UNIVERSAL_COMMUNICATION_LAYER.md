# Universal Communication Layer — first increment

## Scope

This package provides the initial primitives for communication adapter discovery, secret-redacted capture, and explicitly authorized replay. It is intentionally separate from `app.domain.tools.ToolRegistry`: that registry stores versioned tool manifests, while `CommunicationRegistry` stores live adapter instances.

## Contracts

- `CommunicationRequest`: adapter, protocol, operation, payload, metadata, and correlation ID.
- `CommunicationRegistry`: explicit registration and resolution of adapter instances implementing `execute(operation, payload, *, context)`.
- `CommunicationCapture`: append-only JSONL records. Nested credential-like fields, bearer values, and common credential query parameters are redacted before persistence.
- `CommunicationReplay`: loads a capture, applies non-secret payload overrides, requires an injected authorizer, then calls the registered adapter.

## Security invariants

1. A capture is a replay template, never an authorization grant.
2. Replay fails closed when no authorizer is configured or approval is denied.
3. Credential-like override keys are rejected. Secrets must be resolved at execution time by a trusted adapter/credential provider.
4. The authorizer receives redacted payload and runtime context. The adapter receives the original runtime context so a trusted credential resolver can inject secrets without persisting them.
5. Adapter IDs resolve only through the explicit in-process registry. Captured records cannot import code or instantiate arbitrary classes.
6. The adapter must validate its own operation allowlist, destination policy, and side-effect semantics.

## First concrete provider: ChatGPT Plan

`ChatGPTPlanCommunicationAdapter` wraps the existing locally authorized Sign in with ChatGPT OAuth flow and public Responses API client. It exposes the allowlisted `send_prompt` operation through the same adapter interface. The MCP prompt tool dispatches through the canonical `ToolDispatcher`, versioned `config/tool_registry.json` manifest, `HostToolAuthorizationPolicy`, session capability check, rate limit, output-schema validation, and JSONL tool audit sink. Adapter discovery remains read-only and shares the same in-process `CommunicationRegistry` instance.

The prompt operation requires a separate one-time session pairing created with `--profile termux_communication`. That profile grants only `communication.chatgpt.prompt`; it does not grant Termux shell execution. The existing `termux_developer` profile remains limited to `android.shell.exec`. Revoke or replace the session through the Android shell session controls when access should end. The local session gateway enforces a 24-hour idle lease after pairing and renews it only when an authorized operation is used.

Prompt capture is opt-in: pass `capture=true` to `chatgpt_plan_prompt`. The default is `false`. The default JSONL path is `~/.local/share/jarvis/communication/captures.jsonl`; `JARVIS_COMMUNICATION_CAPTURE_FILE` can override it. The capture directory and file are restricted to owner access on POSIX systems. A successful capture returns `capture_id`. Captured prompts and responses are user content, so enable capture only when local retention is intended.

## Current limitations

- JSONL capture is append-only but does not yet provide cross-process locking, tamper evidence, retention, or encryption at rest.
- Registry lifecycle is in-process; it does not discover or load plugins automatically.
- Replay is synchronous and delegates protocol-specific behavior, authentication, retries, and idempotency to the adapter.
- Replay is not yet exposed as an MCP tool. It remains an internal primitive until a production authorizer is bound to the existing toolbox/session authorization system and a durable pre-execution journal is available.
- Other Android and network protocols are not yet registered as communication adapters. Each new operation needs a versioned manifest, explicit capability, session/approval policy, rate/timeout limits, and output schema; do not expose raw adapter execution directly through MCP.
- A successful adapter call followed by a capture write failure can leave an unrecorded side effect. Production execution needs a durable pre-execution intent/event journal before enabling replay of side-effecting operations.

## Adapter interface

```python
class ExampleAdapter:
    adapter_id = "example.http"

    def execute(self, operation, payload, *, context):
        # Validate operation and destination; resolve credentials locally.
        ...
```

## Tests

Run the isolated contract suite without repository-wide coverage collection:

```bash
python -m pytest -q -o addopts='' tests/communication/test_core.py
```
