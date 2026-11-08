# Jarvis Continual Learning — Wake / Sleep Architecture

**Status:** architecture proposal; no runtime activation and no model-weight training enabled.
**Roadmap dependency:** C0 must close before implementation; capability work belongs to C8 (Learning & Evolution).
**Scope:** provider-neutral learning system for Jarvis OS and the existing Jarvis_Xerife Harness.

## 1. Objective

Build a Jarvis-owned learning process that converts verified operational experience into durable knowledge, better procedures, improved decision policies and, later, specialized model adapters.

The objective is not to train a frontier LLM from scratch, reproduce a proprietary Gemini implementation, or let a model rewrite its own weights/code without controls. External and open models act as teachers, critics and specialist inference providers. Jarvis owns the experience lifecycle, evaluation data, memory, learning policy, experiment history and promotion gates.

The design is inspired by Google Research's October 27, 2026 Sleep framework and the related continual-learning research. The published framework describes two stages: (1) memory consolidation / knowledge seeding and (2) dreaming, which generates and filters synthetic practice data before refinement. This document adapts those ideas to Jarvis; it does not claim the commercial Gemini product uses this exact mechanism.

## 2. Existing components to audit and reuse

C0 remains open. These are reuse candidates, not proof that an end-to-end learning loop is operational.

| Existing component | Intended role | Current evidence / limitation |
|---|---|---|
| `app/application/services/assistant_learning.py` | Capture interactions and retrieve internal solutions | Helper functions call a Nexus `learning_loop`; actual provider registration and complete consumer path still require audit |
| `RewardSignalProvider` | Outcome/reward signals and experience replay | JSONL replay buffer and reward calculations exist; scalar reward is not a correctness oracle |
| `WorkingMemory` + `MemoryConsolidationService` | Short-term experience and durable semantic consolidation | Existing transfer to vector memory; not model-weight training |
| `VectorMemoryAdapter` / `SupabaseVectorMemoryStore` | Durable, scoped retrieval | Adapter and migration exist; runtime read/write evidence and retention/erasure remain C0 gaps |
| `ProceduralMemoryAdapter` | Reusable procedures | Bootstrap and runtime population need verification |
| `ModelRegistry` / `ModelRuntimeBindings` | Provider-neutral model capability registry and runtime binding | Contracts exist; health-aware selection and unified routing remain incomplete |
| `EvolutionOrchestrator`, `EvolutionSandbox`, `EvolutionGatekeeper` | Code/skill evolution proposal, isolated tests and promotion controls | Reuse only through the existing PR, sandbox, policy and human-review gates |
| `AgentTaskQueueService` | Durable scheduling and worker coordination | Reuse; do not create a second scheduler for sleep jobs |
| Cognitive Roadmap C0-C8 | Capability order and acceptance gates | C0 remains open; sleep learning is part of C8, not a shortcut around C0-C7 |

## 3. Wake phase — experience capture

Wake is the normal operating phase. It must not train model weights inline with user requests.

Capture an `ExperienceEpisode` only when a useful outcome can be observed. A versioned episode should contain, subject to privacy policy:

- episode ID, tenant/user scope and schema version;
- task type, goal reference and relevant context references;
- selected model/provider/runtime and skill/tool versions;
- input/output references or minimized structured features (not indiscriminate raw transcripts);
- decision, predicted outcome and confidence where available;
- independently observed outcome, evidence references and evaluator;
- latency, token/cost estimate, retries and resource usage;
- human feedback or explicit correction, if present;
- sensitivity, consent/policy basis, retention class and redaction status.

Separate these labels:
- **Observed outcome:** independently verified event/result.
- **Human judgment:** explicit user acceptance/correction.
- **Model judgment:** teacher or critic estimate.
- **Inferred reward:** derived score with a documented formula.

Never treat a model's self-reported success as ground truth. Missing or ambiguous outcomes remain unlabeled and are not used as positive training examples.

## 4. Sleep phase — bounded offline learning

Sleep is a scheduled, interruptible maintenance workflow. It starts only when the host is idle enough, the learning budget is available and no critical foreground task is being starved. It supports CPU-only operation and optional GPU acceleration. It must be cancellable and resumable.

### 4.1 Select and sanitize

1. Read eligible episodes through existing storage ports.
2. Enforce tenant scope, consent, retention and recursive redaction.
3. Remove secrets, duplicate samples and low-information records.
4. Preserve provenance and label quality.
5. Quarantine contradictory, uncertain or model-only labels rather than silently accepting them.

### 4.2 Consolidate knowledge

Produce versioned candidate artifacts:
- semantic memory updates (facts with provenance, validity and contradiction links);
- procedural memory / skill candidates (steps, preconditions, expected result and failure modes);
- decision examples for intent/task classification;
- unresolved questions and capability gaps.

Do not convert every conversation into permanent memory. Consolidation is selective, deduplicated, scoped and reversible.

### 4.3 Dreaming / synthetic curriculum

Generate practice tasks from real failure clusters, under-covered categories and changed environments. Vary surface form and context to test generalization.

Use multiple independent sources where practical: deterministic validators, test suites, real outcomes, and separate teacher/critic models. Self-judging alone is insufficient. Synthetic examples must be marked as synthetic and must never be mixed with verified observations without labels.

### 4.4 Evaluate before learning

Every candidate must run against:
- a frozen baseline suite;
- a time-separated holdout not used for generation or training;
- regression suites for previously working skills;
- adversarial, ambiguous and out-of-distribution examples;
- latency, cost, memory and resource measurements.

Report per-task accuracy, precision/recall where applicable, calibration (e.g. Brier score / ECE), abstention quality, regression/forgetting delta, latency and cost. Thresholds come from C0 baseline measurements; do not invent them.

### 4.5 Progressive adaptation ladder

Use the least risky adaptation that solves the measured problem:

1. **Memory / retrieval:** consolidate a verified fact or procedure; no weight changes.
2. **Skill / prompt / policy:** propose a versioned skill or deterministic rule; validate through existing tests and PR workflow.
3. **Small decision model:** train or calibrate a compact classifier/ranker for bounded tasks such as intent, routing or confidence estimation.
4. **Parameter-efficient adapter:** only when the evaluation proves memory/prompt/policy is insufficient, train an isolated LoRA/PEFT adapter while keeping the base model frozen.
5. **Base-model fine-tuning:** out of initial scope; requires a separate ADR, dataset review, compute budget, reproducibility plan and explicit approval.

Every learned artifact is versioned and independently switchable. Never overwrite the active model or adapter in place.

## 5. Proposed module boundaries

These are logical boundaries; exact paths and ports must be finalized after C0 maps existing consumers and dependencies.

- `ExperienceCapture`: receives verified task/outcome events and produces sanitized episodes.
- `ExperienceRepository`: storage port; initially adapts existing replay/memory stores where their semantics fit.
- `LearningEligibilityPolicy`: decides which episodes may be retained or trained on.
- `SleepOrchestrator`: schedules, leases, checkpoints, budgets, cancellation and resumability; delegates work to the existing queue/runtime.
- `MemoryConsolidator`: prepares semantic/procedural memory candidates.
- `DreamCurriculumGenerator`: generates labeled synthetic practice cases.
- `LearningEvaluator`: baseline/holdout/regression evaluation and report generation.
- `AdapterTrainer`: optional isolated PyTorch + Transformers/PEFT training runtime; never imported by the portable Jarvis core.
- `LearningArtifactRegistry`: versions datasets, memory/skill candidates, adapters and evaluation reports.
- `LearningPromotionGate`: promotes only evaluated artifacts; uses existing Gatekeeper, sandbox, PR and human approval controls.

No new event bus, scheduler, memory database or provider SDK dependency is justified until C0 proves the existing equivalent cannot satisfy the contract.

## 6. Model ecosystem

Model providers are replaceable roles, not the identity of Jarvis:

- **Fast specialist:** small local model (Laya is one candidate) for low-latency typed decisions.
- **Teacher / researcher:** currently available free-tier or open-source-capable providers (e.g. Gemini, Groq, Venice, Kimi where access and terms permit) to explain, label or generate candidate curricula.
- **Local student:** a compact open-weight model selected only after the dedicated SSD host's CPU, RAM, GPU, VRAM, driver and disk capacity are measured.
- **Critic / verifier:** a different model or deterministic evaluator; avoid a single-model feedback loop.
- **Training runtime:** separate Python environment with PyTorch and optional CUDA/PEFT; exposed to Jarvis through a narrow authenticated local API or job artifact contract.

Provider outputs are untrusted data. They cannot change authorization, tool permissions, scheduler priority, production configuration or active model versions.

## 7. Jarvis OS placement and hardware boundary

Jarvis OS owns the host lifecycle and resource policy; Jarvis Intelligence owns learning semantics. The Harness remains portable and useful on Windows/Linux/macOS.

The dedicated SSD is the intended Jarvis OS target, but installation is blocked until read-only inventory confirms the exact physical disk identity, model, serial, capacity, partition table and current volumes. Never select a disk by drive letter alone. Never format or repartition the Windows system disk. The first Linux validation remains a disposable VM; the physical SSD install is a later, explicitly verified operation.

Recommended filesystem placement is intentionally not fixed until disk capacity is known. Keep OS, persistent Jarvis data, model cache/checkpoints and temporary training workspace separable so model downloads cannot exhaust the root filesystem. Do not download model weights before measuring available space.

## 8. Safety, rollback and observability

- Sleep jobs are opt-in, bounded by CPU/RAM/VRAM/disk/time budgets and preemptible.
- No live user request waits for training; no training process can block the primary agent queue.
- Data isolation and redaction happen before teacher calls or training.
- Every run records dataset manifest/hash, base model revision, adapter revision, trainer/library versions, seed, hyperparameters, hardware profile, metrics and artifact hashes.
- Promotion is staged: candidate -> offline evaluation -> shadow/canary -> explicit approval -> active version.
- Rollback restores the previous artifact atomically.
- A failed or interrupted sleep cycle leaves the active memory/model unchanged.
- The learning engine cannot modify its own authorization policies, secrets, safety rules, protected paths or CI thresholds.
- Code changes continue through separate PRs, green CI, review and existing self-healing controls.

## 9. Implementation sequence

1. Close C0 evidence gaps for learning, memory, providers, queue, privacy and OS host inventory.
2. Add behavioral baseline tests for episode capture, provenance, isolation and outcome labels.
3. Define versioned episode and learning-artifact contracts without adding a new database until existing stores are proven insufficient.
4. Implement a dry-run SleepOrchestrator using existing queue/worker lifecycle; produce reports only.
5. Implement selective memory/procedural consolidation with replay and idempotency.
6. Implement synthetic curriculum generation and independent evaluation; no weight updates.
7. Add a compact decision/ranker experiment using a frozen model and measured baseline.
8. Add optional PEFT/LoRA training in a separate environment only after a GPU/CPU profile and evaluation gates justify it.
9. Validate the complete lifecycle in a disposable Linux VM, then validate Jarvis OS boot and hardware services on the dedicated SSD without touching Windows.

## 10. Definition of done for the first sleep-learning slice

- A real task with independently verified outcome creates one scoped, redacted episode.
- Replaying the same event does not create a duplicate.
- A dry-run sleep cycle selects eligible episodes and explains exclusions.
- Consolidation produces versioned candidates and preserves the original records.
- Synthetic tasks are marked and evaluated separately from observed examples.
- Baseline and holdout metrics are reproducible.
- An interrupted/failed cycle leaves active memory and model unchanged.
- No parameter update, code publication, external action or permission change occurs in the first slice.
