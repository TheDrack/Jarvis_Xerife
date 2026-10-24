---
name: jarvis-android-navigation
description: Use the optional ARTEMIS-backed Android UI navigation adapter without altering desktop navigation or existing MacroDroid device-control paths.
---

# Jarvis Android Navigation

Use this skill when the user asks an agent to navigate an Android app or Android system UI autonomously.

## Rules

1. Keep Android navigation separate from desktop visual navigation and existing MacroDroid commands.
2. Resolve a registered, authorized Android device and pass its exact serial as `device_id`. Never silently select a different device.
3. Prefer the `pro` profile for multi-step workflows, uncertain UI, or tasks needing checkpoints and final verification. Use `flash` only for simple, low-risk actions.
4. Observe and verify the result. A successful tool invocation alone is not proof that the requested UI state was reached; inspect the returned task status and trace.
5. If the task fails, inspect the trace and current device state before retrying. Do not blindly repeat actions with possible side effects.
6. Ask before destructive actions, purchases, sending messages, or changing security/privacy settings when the user's intent does not clearly authorize that exact action.
7. Do not install software, enable USB debugging, or alter phone settings without explicit authorization.
8. Keep ARTEMIS endpoints private and credentials out of prompts and logs.
9. The initial adapter is opt-in and does not auto-register devices or change the existing leader's routing. Integration into device dispatch requires a separate tested change.
