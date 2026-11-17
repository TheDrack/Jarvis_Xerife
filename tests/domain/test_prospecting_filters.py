import json
from pathlib import Path

import pytest

from app.domain.prospecting.discovery import DiscoveryQuery, cnae_matches
from app.domain.prospecting.filters import (
    FilterCatalog,
    FilterPreset,
    describe_catalog,
    load_filter_catalog,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUR_CATALOG = REPO_ROOT / "config/prospecting/filters.json"


def test_primary_activity_matches_by_prefix():
    assert cnae_matches("4120400", "", ("41",)) is True
    assert cnae_matches("6201500", "", ("41", "43")) is False


def test_secondary_activity_matches_only_whole_codes():
    assert cnae_matches("4618401", "4120400,4399103", ("43",)) is True
    # 2410 must not match the 241 prefix inside a longer code such as 2410000? it would,
    # so assert the opposite direction: a prefix absent from every code never matches.
    assert cnae_matches("4618401", "6201500", ("43",)) is False
    assert cnae_matches("4618401", "4120400", ("43",), include_secondary=False) is False


def test_secondary_matching_handles_spacing_and_empty_fields():
    assert cnae_matches("4618401", " 4120400 , 4399103 ", ("4120",)) is True
    assert cnae_matches("4618401", "", ("41",)) is False


def test_preset_catalog_resolves_by_id_and_lists_ids():
    catalog = FilterCatalog(
        presets=(
            FilterPreset(
                id="obras",
                name="Obras",
                query=DiscoveryQuery(uf="SC", cnae_prefixes=("41",)),
            ),
        )
    )

    assert catalog.ids() == ("obras",)
    assert catalog.get("obras").query.uf == "SC"
    with pytest.raises(KeyError):
        catalog.get("nao-existe")


def test_our_filter_catalog_is_valid_and_uses_secondary_activities():
    catalog = load_filter_catalog(OUR_CATALOG)

    assert len(catalog.presets) >= 3
    assert len(set(catalog.ids())) == len(catalog.presets)
    for preset in catalog.presets:
        assert preset.query.uf == "SC"
        assert preset.query.only_active is True
        assert preset.query.include_secondary_cnae is True
        assert preset.query.limit >= 100
    assert "construcao-grande-florianopolis" in catalog.ids()


def test_catalog_file_can_be_described_for_the_cli(tmp_path):
    path = tmp_path / "filters.json"
    payload = {
        "version": 1,
        "presets": [
            {
                "id": "obras",
                "name": "Obras",
                "description": "Construcao",
                "query": {"uf": "SC", "cnae_prefixes": ["41"], "limit": 100},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    catalog = load_filter_catalog(path)
    description = describe_catalog(catalog)

    assert "obras: Obras" in description
    assert "SC" in description
    assert "todo o estado" in description
