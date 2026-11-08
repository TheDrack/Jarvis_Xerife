# Laya Decision Engine — Shadow Mode POC

**Status:** opt-in proof of concept; shadow-only.  
**Default:** disabled.  
**Execution authority:** none.

## Scope

Jarvis may call a self-hosted Laya /predict endpoint to classify a bounded text request into the existing router task categories. The result is recorded for comparison only. It must not change LLMRouter selection, scheduler priority, tool authorization, task execution, or user-facing responses.

The integration uses a provider-neutral DecisionEngine port and an HTTP adapter. Laya/PyTorch is not imported into the Jarvis core environment; the model runs as a separately managed local service.

## Enable locally

Start a self-hosted Laya service using the upstream project's documented laya[serve] extra. Then set:

- JARVIS_LAYA_SHADOW_ENABLED=true
- JARVIS_LAYA_BASE_URL=http://127.0.0.1:8000
- JARVIS_LAYA_API_KEY only when the Laya service has LAYA_API_KEY configured
- JARVIS_LAYA_TIMEOUT_SECONDS=0.8 (optional; default 0.8)

The adapter accepts loopback HTTP or HTTPS. Non-loopback endpoints require HTTPS. The feature remains disabled unless explicitly enabled.

## Shadow behavior

LLMRouter.execute() submits the user/task text to a bounded background executor. The existing deterministic router continues immediately and remains authoritative. When the queue is full, the sample is dropped. A failed or unavailable Laya service is logged at debug level and does not affect the request.

The event contains only the predicted category, existing category, agreement, confidence and selected Laya checkpoint. It deliberately excludes prompt text, credentials and raw provider payloads. An optional event sink can be injected for tests or a future approved telemetry adapter.

## Initial taxonomy

- code_repair
- code_generation
- planning
- evolution
- vision
- general

This taxonomy mirrors the current LLMRouter task categories. It is not a universal intent taxonomy and does not yet classify proactive assistance or scheduler priority.

## Evaluation gates

Do not promote Laya decisions into active routing until a Portuguese-heavy, representative labelled dataset exists and held-out evaluation demonstrates per-class precision/recall, confusion matrix, confidence calibration, abstention coverage, target-hardware latency, and no regression in routing, queue semantics or authorization.

The upstream README warns that base checkpoints are weak on zero-shot typed decisions and that the 0.766 typed-decision benchmark score belongs to a fine-tuned checkpoint. Treat confidence as a model signal, not a safety guarantee.

## Explicit non-goals

- No automatic installation or download of model weights.
- No model-driven tool execution or authorization.
- No automatic scheduler priority changes.
- No active replacement of intent normalization or LLM routing.
- No persistence of raw user prompts.
- No mandatory Laya dependency for portable Harness deployments.
