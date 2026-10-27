# Capability aliases and semantic action names

## Purpose

JARVIS can use compact internal aliases for UI controls, tools, actions, and higher-level intents without coupling plans to visible button labels. Aliases are a naming and abstraction layer only: they do not hide the canonical action from authorization, confirmation, or audit.

## Model

- **Alias**: stable internal handle such as `SCOPE-01`.
- **Intent**: semantic purpose, such as `inspect_desktop`.
- **Canonical capability ID**: the actual operation, such as `desktop.inspect`.
- **Permission**: policy requirement evaluated against the canonical capability.
- **Postcondition**: the observable result expected after execution (owned by the caller/workflow and should be checked after an action).
- **Audit event**: records alias, intent, canonical capability, permission, and outcome.

Do not use aliases to misrepresent an action, suppress disclosure required by the interface, or bypass platform, OS, user, or application security controls. A denied operation remains denied regardless of its alias.

## Example

```python
from app.domain.models.capability_alias_registry import Capability, CapabilityAliasRegistry

registry = CapabilityAliasRegistry()
registry.register_capability(Capability(
    capability_id="desktop.inspect",
    description="Inspect desktop state",
    handler=lambda payload: {"target": payload.get("target", "desktop")},
    required_permission="desktop.read",
))
registry.register_alias("SCOPE-01", "desktop.inspect", "inspect_desktop")

audit_events = []
result = registry.execute(
    "SCOPE-01",
    {"target": "task_scheduler"},
    authorize=lambda capability_id, permission: (
        capability_id == "desktop.inspect" and permission == "desktop.read"
    ),
    audit=audit_events.append,
)
```

## Execution contract

1. Resolve the alias to a registered canonical capability.
2. Evaluate authorization using the canonical ID and declared permission.
3. Require explicit confirmation when the capability says it is required.
4. Execute the registered handler only after checks pass.
5. Emit an audit record for success, denial, and missing confirmation.
6. Verify the workflow postcondition independently; handler completion alone does not prove that the requested state was achieved.

The registry is an opt-in domain component in this change. Existing adapters and UI workflows are not silently rewired; integration must happen deliberately at their capability boundary, with adapter-specific tests.
