"""Thread-safe in-memory registry for versioned tool manifests."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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
                    f"tool manifest already registered: {snapshot.tool_id}@{snapshot.version}"
                )
            self._manifests[key] = snapshot

        return snapshot.model_copy(deep=True)

    def get(self, tool_id: str, version: str) -> ToolManifest | None:
        """Return an isolated snapshot for an exact tool ID and version."""
        with self._lock:
            manifest = self._manifests.get((tool_id, version))
            return manifest.model_copy(deep=True) if manifest is not None else None

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

        return tuple(sorted(matches, key=lambda item: (item.tool_id, item.version)))

    def list_manifests(self) -> tuple[ToolManifest, ...]:
        """Return a stable, isolated snapshot of every registered manifest."""
        with self._lock:
            manifests = [
                manifest.model_copy(deep=True)
                for manifest in self._manifests.values()
            ]

        return tuple(sorted(manifests, key=lambda item: (item.tool_id, item.version)))

    def __len__(self) -> int:
        with self._lock:
            return len(self._manifests)
