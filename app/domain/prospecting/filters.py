"""Predefined filter sets, chosen at run time.

A campaign fixes the buyer profile; the filter is the market slice. Keeping the
slices in one catalog means the operator picks a named combination at the moment
of the run ("construction in Grande Florianópolis", "metalworking in SC") instead
of editing JSON per search, and every combination stays inspectable and
versioned.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.domain.prospecting.discovery import DiscoveryQuery


class FilterPreset(BaseModel):
    """One named, reusable market slice."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    query: DiscoveryQuery


class FilterCatalog(BaseModel):
    """All presets, with lookup by id and a stable, printable order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(default=1, ge=1)
    presets: tuple[FilterPreset, ...] = ()

    def get(self, preset_id: str) -> FilterPreset:
        for preset in self.presets:
            if preset.id == preset_id:
                return preset
        known = ", ".join(preset.id for preset in self.presets) or "(none)"
        raise KeyError(f"unknown filter preset {preset_id!r}; available: {known}")

    def ids(self) -> tuple[str, ...]:
        return tuple(preset.id for preset in self.presets)


def load_filter_catalog(path: Path | str) -> FilterCatalog:
    """Load the catalog, failing loudly on typos rather than guessing."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return FilterCatalog.model_validate(payload)


def describe_catalog(catalog: FilterCatalog) -> str:
    """Human-readable listing for the CLI."""
    if not catalog.presets:
        return "no filter presets found"
    lines: list[str] = []
    for preset in catalog.presets:
        query = preset.query
        cities = ", ".join(query.municipalities) or "todo o estado"
        lines.append(
            f"{preset.id}: {preset.name}\n"
            f"  {query.uf} | {cities} | CNAE {', '.join(query.cnae_prefixes)}"
            f"{'' if query.include_secondary_cnae else ' (so principal)'}"
        )
        if preset.description:
            lines.append(f"  {preset.description}")
    return "\n".join(lines)


__all__ = [
    "FilterCatalog",
    "FilterPreset",
    "describe_catalog",
    "load_filter_catalog",
]
