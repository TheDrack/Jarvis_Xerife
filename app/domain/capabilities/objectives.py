# -*- coding: utf-8 -*-
"""Roadmap objectives — the ``objective:`` namespace (ADR-006, refactor R1).

``data/capabilities.json`` is the cognitive roadmap, not the execution catalog.
Its entries answer "what long-term goal are we pursuing", never "which
implementation serves this capability on this host". To keep the two apart,
objective identifiers use the explicit ``objective:CAP-###`` namespace, while
executable capabilities use ``capability:<name>`` (see
``app/application/services/capability_binding_registry.py``).

Status vocabulary:

``pending``
    Not started.
``partial``
    Started, known to be incomplete.
``unverified``
    Claimed as done by source reading or heuristic notes, **without** recorded
    execution evidence. This is the honest state for a heuristic claim: it is
    not ``complete`` and it does not pretend to be ``pending``.
``complete``
    Requires an ``evidence`` object with ``command``, ``result`` (``passed``)
    and ``recorded_at``. Nothing else qualifies.
``blocked``
    Cannot advance until an external condition changes.

``claimed_status`` preserves a retired heuristic claim (for example
``complete``) without asserting it, so the history is not deleted.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Tuple

OBJECTIVE_NAMESPACE = "objective:"
OBJECTIVE_ID_PATTERN = re.compile(r"^objective:CAP-[0-9]{3}$")
_LEGACY_ID_PATTERN = re.compile(r"^CAP-[0-9]{3}$")
CAPABILITY_NAMESPACE = "capability:"

OBJECTIVE_STATUSES = frozenset(
    {"pending", "partial", "unverified", "complete", "blocked"}
)
EXECUTION_EVIDENCE_FIELDS = ("command", "result", "recorded_at")
EXECUTION_RESULT_PASSED = "passed"


class ObjectiveCatalogError(ValueError):
    """The objective catalog is malformed or claims a state it cannot prove."""


def is_objective_id(value: object) -> bool:
    """Return whether *value* is a canonical ``objective:CAP-###`` identifier."""
    return isinstance(value, str) and bool(OBJECTIVE_ID_PATTERN.fullmatch(value))


def normalize_objective_id(value: str) -> str:
    """Return the canonical ``objective:CAP-###`` identifier.

    Accepts ``CAP-042`` (the legacy on-disk form) and
    ``objective:CAP-042``. Refuses ``capability:*`` identifiers: executable
    capabilities are not roadmap objectives, and comparing the two namespaces
    is the defect ADR-006 R1 removes.
    """
    if not isinstance(value, str) or not value.strip():
        raise ObjectiveCatalogError("objective identifier must be a non-empty string")
    text = value.strip()
    if text.startswith(CAPABILITY_NAMESPACE):
        raise ObjectiveCatalogError(
            f"capability identifiers are executable, not roadmap objectives: {value!r}"
        )
    body = (
        text[len(OBJECTIVE_NAMESPACE) :]
        if text.startswith(OBJECTIVE_NAMESPACE)
        else text
    )
    if not _LEGACY_ID_PATTERN.fullmatch(body):
        raise ObjectiveCatalogError(f"invalid objective identifier: {value!r}")
    return f"{OBJECTIVE_NAMESPACE}{body}"


def validate_execution_evidence(evidence: object) -> dict[str, str]:
    """Validate the evidence required to declare an objective ``complete``."""
    if not isinstance(evidence, Mapping):
        raise ObjectiveCatalogError(
            "status 'complete' requires an execution evidence object"
        )

    normalized: dict[str, str] = {}
    for field in EXECUTION_EVIDENCE_FIELDS:
        value = evidence.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ObjectiveCatalogError(
                f"execution evidence is missing a non-empty {field!r}"
            )
        normalized[field] = value.strip()

    if normalized["result"] != EXECUTION_RESULT_PASSED:
        raise ObjectiveCatalogError(
            "execution evidence must record result "
            f"{EXECUTION_RESULT_PASSED!r}, got {normalized['result']!r}"
        )
    return normalized


def validate_objective(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one objective entry and return its normalized fields."""
    if not isinstance(entry, Mapping):
        raise ObjectiveCatalogError("objective entry must be an object")

    identifier = entry.get("id")
    if not is_objective_id(identifier):
        raise ObjectiveCatalogError(
            "objective id must use the 'objective:' namespace "
            f"(objective:CAP-###): {identifier!r}"
        )

    status = entry.get("status")
    if status not in OBJECTIVE_STATUSES:
        raise ObjectiveCatalogError(
            f"invalid objective status for {identifier}: {status!r}"
        )

    dependencies = entry.get("depends_on", [])
    if not isinstance(dependencies, list) or any(
        not is_objective_id(dependency) for dependency in dependencies
    ):
        raise ObjectiveCatalogError(
            f"depends_on of {identifier} must list objective:CAP-### identifiers"
        )
    if len(set(dependencies)) != len(dependencies):
        raise ObjectiveCatalogError(f"depends_on of {identifier} contains duplicates")

    claimed_status = entry.get("claimed_status")
    if claimed_status is not None:
        if claimed_status not in OBJECTIVE_STATUSES:
            raise ObjectiveCatalogError(
                f"invalid claimed_status for {identifier}: {claimed_status!r}"
            )
        if claimed_status == status:
            raise ObjectiveCatalogError(
                f"claimed_status of {identifier} must differ from status"
            )

    evidence: dict[str, str] | None = None
    if status == "complete":
        evidence = validate_execution_evidence(entry.get("evidence"))

    return {
        "id": identifier,
        "status": status,
        "depends_on": list(dependencies),
        "claimed_status": claimed_status,
        "evidence": evidence,
    }


def validate_catalog(payload: Any) -> Tuple[dict[str, Any], ...]:
    """Validate the whole objective catalog: namespace, dependencies, evidence."""
    if not isinstance(payload, Mapping):
        raise ObjectiveCatalogError("objective catalog must be an object")

    entries = payload.get("capabilities")
    if not isinstance(entries, list):
        raise ObjectiveCatalogError("objective catalog must contain a capabilities list")

    validated = []
    seen: set[str] = set()
    for entry in entries:
        item = validate_objective(entry)
        if item["id"] in seen:
            raise ObjectiveCatalogError(f"duplicate objective id: {item['id']}")
        seen.add(item["id"])
        validated.append(item)

    for item in validated:
        for dependency in item["depends_on"]:
            if dependency == item["id"]:
                raise ObjectiveCatalogError(
                    f"objective {item['id']} depends on itself"
                )
            if dependency not in seen:
                raise ObjectiveCatalogError(
                    f"objective {item['id']} depends on unknown objective: {dependency}"
                )

    return tuple(validated)
