"""Thread-safe in-memory registry for versioned tool manifests."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from threading import RLock
from typing import Any

from app.domain.tools.contracts import ToolManifest


class DuplicateToolManifestError(ValueError):
    """Raised when a tool ID/version is registered more than once."""


class ToolRegistry:
    """Metadata-only registry with deterministic, exact-version lookup.

    This registry does not resolve Nexus components, check adapter health,
    authorize callers, fetch credentials, or execute tools. Those responsibilities
    belong to the future dispatcher/execution broker.
    """

    def __init__(self, manifests: Iterable[ToolManifest] = ()) -> None:
        self._lock = RLock()
        self._manifests: dict[tuple[str, str], ToolManifest] = {}
        for manifest in manifests:
            self.register(manifest)

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "ToolRegistry":
        """Load the canonical manifest catalog from a versioned JSON file."""
        registry_path = (
            Path(path)
            if path is not None
            else Path(__file__).resolve().parents[3]
            / "config"
            / "tool_registry.json"
        )
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(
            payload.get("tools"), list
        ):
            raise ValueError(
                "tool registry file must contain an object with a tools list"
            )
        schema_version = payload.get("schema_version")
        if not isinstance(schema_version, str) or not re.fullmatch(
            r"\d+\.\d+\.\d+", schema_version
        ):
            raise ValueError(
                "tool registry must declare a semantic schema_version"
            )
        return cls(payload["tools"])

    def register(
        self,
        manifest: ToolManifest | Mapping[str, Any],
        *,
        replace: bool = False,
    ) -> ToolManifest:
        """Register a manifest snapshot.

        Replacing an existing tool/version is explicit. A caller must request an
        exact version; the registry never silently chooses a "latest" version.
        """
        normalized = (
            manifest
            if isinstance(manifest, ToolManifest)
            else ToolManifest.model_validate(manifest)
        )
        snapshot = normalized.model_copy(deep=True)
        key = (snapshot.tool_id, snapshot.version)

        with self._lock:
            if key in self._manifests and not replace:
                raise DuplicateToolManifestError(
                    f"tool manifest already registered: {
                        snapshot.tool_id}@{
                        snapshot.version}"
                )
            self._manifests[key] = snapshot

        return snapshot.model_copy(deep=True)

    def get(
        self, tool_id: str, version: str | None = None
    ) -> ToolManifest | None:
        """Return an exact version, or the sole registered version during migration."""
        if version is None:
            return self.get_unique(tool_id)
        with self._lock:
            manifest = self._manifests.get((tool_id, version))
            return (
                manifest.model_copy(deep=True)
                if manifest is not None
                else None
            )

    def get_unique(self, tool_id: str) -> ToolManifest | None:
        """Resolve an omitted version only when exactly one version is registered."""
        with self._lock:
            matches = [
                manifest
                for (registered_id, _), manifest in self._manifests.items()
                if registered_id == tool_id
            ]
            if len(matches) > 1:
                raise ValueError(
                    f"tool_version is required when multiple versions exist: {tool_id}"
                )
            return matches[0].model_copy(deep=True) if matches else None

    def find_by_capability(self, capability: str) -> tuple[ToolManifest, ...]:
        """Find tools by exact capability match; substring matches are forbidden."""
        if not isinstance(capability, str) or not capability.strip():
            raise ValueError("capability must be a non-empty string")

        with self._lock:
            matches = [
                manifest.model_copy(deep=True)
                for manifest in self._manifests.values()
                if capability in manifest.capabilities
            ]

        return tuple(
            sorted(matches, key=lambda item: (item.tool_id, item.version))
        )

    def list_manifests(self) -> tuple[ToolManifest, ...]:
        """Return a stable, isolated snapshot of every registered manifest."""
        with self._lock:
            manifests = [
                manifest.model_copy(deep=True)
                for manifest in self._manifests.values()
            ]

        return tuple(
            sorted(manifests, key=lambda item: (item.tool_id, item.version))
        )

    def list_tools(self, *, enabled_only: bool = False) -> list[ToolManifest]:
        """Compatibility view used by runtime discovery; ordering remains stable."""
        manifests = self.list_manifests()
        if enabled_only:
            manifests = tuple(item for item in manifests if item.enabled)
        return list(manifests)

    def __len__(self) -> int:
        with self._lock:
            return len(self._manifests)

[executed on device: DESKTOP-HPJ82UA (d504f4a4-8a27-4cc9-94f5-7abc9b926b55)]