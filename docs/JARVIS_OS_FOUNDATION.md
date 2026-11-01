# Jarvis OS Foundation — JOF 0.1

## Objective

Prepare the existing Jarvis_Xerife repository to serve as a modular, provider-neutral harness that can optionally grow into an autonomous host manager and a complete Jarvis OS installation.

The first deliverable is a portable foundation, not a bootable distribution and not a local-LLM deployment.

## Workstreams

### A. Repository reconciliation
- Inventory source modules, entry points, dependency groups, configuration, tests and workflows.
- Map existing implementations to the target architecture.
- Mark each item: reuse, extend, refactor, new, duplicate candidate, or unverified.
- Resolve stale documentation before moving code.

### B. Operating profiles
- Define explicit profiles: harness, autonomy, host, jarvis-os.
- Ensure profile selection is declarative and opt-in.
- Report requested/enabled/available/authorized/tested states separately.
- Keep host-only dependencies out of the portable core.

### C. Provider-neutral model and agent contracts
- Inventory current API and local model adapters.
- Normalize model identity, capabilities, modality, availability, concurrency, cost, latency, reliability, invocation, usage, errors and cancellation.
- Keep provider SDKs inside adapters.
- Remove hard-coded provider assumptions from generic task scheduling only after compatibility tests exist.
- Support multiple providers and runtimes simultaneously, including external agent runtimes.

### D. Multi-agent runtime
- Reuse existing task/message contracts, scheduler and queue.
- Complete heartbeat, health reconciliation, lease renewal, recovery and two-runtime end-to-end tests.
- Preserve at-least-once delivery and idempotency requirements.
- Support an explicit local standalone queue backend without pretending it provides cross-machine coordination.

### E. Host integration
- Add hardware discovery and resource telemetry as optional modules.
- Keep all privileged operations behind typed, policy-checked interfaces.
- Add systemd units and desktop integration only in the OS profile.
- Keep the harness useful on Windows, macOS and Linux.

### F. Image and virtual validation
- First validate the portable harness in a clean Linux virtual environment.
- Then validate host integration in a disposable Linux VM.
- Only after boot, networking, drivers, desktop, recovery and update tests pass, create a bootable image artifact.
- Never overwrite the current workstation disk during prototype testing.

## Initial sequence

1. Architecture and repository map.
2. Profile/configuration contract and compatibility tests.
3. Provider-neutral model/agent contracts.
4. Multi-provider registry and scheduler integration.
5. Local harness packaging and clean-environment test.
6. Optional host manager and systemd integration.
7. Disposable VM boot test.
8. Reproducible image build and release pipeline.

## Definition of done for JOF 0.1

- Architecture is mapped to existing code with evidence.
- Profile and provider-neutral contracts are documented and tested.
- Existing providers remain compatible.
- Multi-provider concurrent execution has deterministic tests.
- Portable install works without OS-level privileges or a configured LLM.
- Clean Linux virtual-environment tests pass.
- No production state, secrets, network policy or existing workstation installation is changed.
