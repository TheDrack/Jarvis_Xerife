# Laya Decision Engine — Shadow Mode POC

**Status:** opt-in proof of concept; shadow-only.  
**Default:** disabled.  
**Execution authority:** none.

## Scope

Jarvis may call a self-hosted Laya /predict endpoint to classify a bounded text request into the existing router task categories. The result is recorded for comparison only. It must not change LLMRouter selection, scheduler priority, tool authorization, task execution, or user-facing responses.

The integration uses a provider-neutral DecisionEngine port and an HTTP adapter. Laya/PyTorch is not imported into the Jarvis core environment; the model runs as a separately managed local service.

## Enable locally

Install and run the upstream server in a separate Python environment (do not install its PyTorch stack into the Jarvis core environment):

```bash
python -m pip install "laya[serve]"
LAYA_DEVICE=cpu LAYA_PRELOAD=1 laya-serve
```

For a CUDA-capable host, use `LAYA_DEVICE=cuda` after installing a PyTorch build compatible with its NVIDIA GPU and driver. For the upstream example playground instead, run `python examples/server.py --device cpu`. Consult the upstream README for its supported flags and checkpoint selection.

Then set:

- JARVIS_LAYA_SHADOW_ENABLED=true
- JARVIS_LAYA_BASE_URL=http://127.0.0.1:8000 (or an HTTPS URL to a remote GPU host)
- JARVIS_LAYA_API_KEY only when the Laya service has LAYA_API_KEY configured
- JARVIS_LAYA_TIMEOUT_SECONDS=0.8 (optional; default 0.8)

The adapter accepts loopback HTTP or HTTPS. Non-loopback endpoints require HTTPS. The feature remains disabled unless explicitly enabled.

## Shadow behavior

LLMRouter.execute() submits the user/task text to a bounded background executor. IntentProcessor also submits the raw user text against the existing CommandType taxonomy, and AgentTaskQueueService.enqueue() compares the objective's task_type against the scheduler's existing classification. The existing parser, router and queue values remain authoritative. When the queue is full, the sample is dropped. A failed or unavailable Laya service is logged at debug level and does not affect the request.

The event contains only the predicted category/value, existing category/value, agreement, confidence and selected Laya checkpoint. It deliberately excludes prompt text, credentials and raw provider payloads. Events are currently emitted through structured logs and an optional injected event sink; persistent analytics storage is not yet wired.

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


## Integration points

- `LLMRouter`: compare the existing `task_type` with Laya's task-category choice.
- `IntentProcessor`: compare the existing `CommandType` with Laya's Portuguese command classification.
- `AgentTaskQueueService.enqueue`: compare the task objective's category with the scheduler's existing `task_type`.

All three integrations are opt-in through the same environment flag and can also receive an injected observer in tests. They never rewrite task type, priority, command type, queue state, or execution behavior.

## GPU placement

The Jarvis service only needs HTTP access to Laya; PyTorch and model checkpoints belong in the separate inference environment. For a cloud GPU, expose the service through a private network or HTTPS with `LAYA_API_KEY`; never expose an unauthenticated inference port to the public internet. Render remains suitable for ordinary Jarvis APIs and coordination, while GPU inference should use a GPU instance/provider that explicitly supplies CUDA-compatible hardware.
