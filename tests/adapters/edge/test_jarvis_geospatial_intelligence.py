from __future__ import annotations

from app.adapters.edge.jarvis_geospatial_intelligence import (
    GeospatialWatchlistStore,
    filter_assets_by_radius,
)


def test_filter_assets_by_radius_returns_only_located_assets_inside_viewport():
    assets = [
        {"id": 1, "name": "near", "latitude": -23.55, "longitude": -46.63,
         "located": True, "location_source": "gps", "approximate": False},
        {"id": 2, "name": "far", "latitude": 40.71, "longitude": -74.00,
         "located": True, "location_source": "ip", "approximate": True},
        {"id": 3, "name": "unknown", "latitude": None, "longitude": None,
         "located": False},
        {"id": 4, "name": "stale coordinates", "latitude": -23.55, "longitude": -46.63,
         "located": False},
    ]

    result = filter_assets_by_radius(
        assets, latitude=-23.56, longitude=-46.64, radius_km=20
    )

    assert [item["id"] for item in result] == [1]
    assert result[0]["distance_km"] < 5
    assert result[0]["approximate"] is False


def test_filter_assets_handles_dateline_and_rejects_invalid_viewport():
    assets = [
        {"id": 1, "latitude": 0, "longitude": 179.8, "located": True},
        {"id": 2, "latitude": 0, "longitude": -179.8, "located": True},
    ]

    result = filter_assets_by_radius(
        assets, latitude=0, longitude=180, radius_km=50
    )

    assert {item["id"] for item in result} == {1, 2}


def test_watchlist_persists_selected_registered_assets_and_initial_observation(tmp_path):
    store = GeospatialWatchlistStore(tmp_path / "geospatial.db")
    asset = {
        "id": 7, "name": "Notebook", "type": "desktop", "status": "online",
        "last_ip": "203.0.113.10", "latitude": -23.55, "longitude": -46.63,
        "located": True, "location_source": "ip", "approximate": True,
        "source": "device_registry",
    }

    added = store.add(asset)

    assert added["asset_id"] == 7
    assert added["last_ip"] == "203.0.113.10"
    assert store.list_assets()[0]["asset_id"] == 7
    history = store.history(7)
    assert len(history) == 1
    assert history[0]["change_type"] == "added"
    assert history[0]["location_source"] == "ip"
    assert history[0]["approximate"] is True


def test_watchlist_records_ip_changes_without_claiming_physical_movement(tmp_path):
    store = GeospatialWatchlistStore(tmp_path / "geospatial.db")
    original = {
        "id": 12, "name": "Phone", "type": "mobile", "status": "online",
        "last_ip": "203.0.113.20", "latitude": -23.55, "longitude": -46.63,
        "located": True, "location_source": "ip", "approximate": True,
    }
    store.add(original)
    unchanged = store.observe(original)
    assert unchanged["changed"] is False
    assert len(store.history(12)) == 1

    updated = {
        **original, "last_ip": "203.0.113.21",
        "latitude": -23.60, "longitude": -46.70,
    }
    result = store.observe(updated)

    assert result["changed"] is True
    assert result["change_type"] == "ip_changed"
    history = store.history(12)
    assert len(history) == 2
    assert history[-1]["previous_ip"] == "203.0.113.20"
    assert history[-1]["current_ip"] == "203.0.113.21"
    assert history[-1]["movement_inferred"] is False
    assert history[-1]["location_confidence"] == "low"


def test_watchlist_requires_a_stable_positive_registered_device_id(tmp_path):
    store = GeospatialWatchlistStore(tmp_path / "geospatial.db")

    try:
        store.add({"id": -1, "name": "discovered"})
    except ValueError as exc:
        assert "registered" in str(exc).lower()
    else:
        raise AssertionError("ephemeral discovered IDs must not enter the watchlist")


def test_remove_watchlist_keeps_observation_history_for_audit(tmp_path):
    store = GeospatialWatchlistStore(tmp_path / "geospatial.db")
    store.add({"id": 4, "name": "Router", "last_ip": "192.0.2.4"})

    assert store.remove(4) is True
    assert store.list_assets() == []
    assert len(store.history(4)) == 1


def test_watchlist_preserves_added_at_when_asset_is_observed_again(tmp_path):
    store = GeospatialWatchlistStore(tmp_path / "geospatial.db")
    original = {
        "id": 19, "name": "Router", "status": "online",
        "last_ip": "192.0.2.19", "located": True,
    }
    added = store.add(original)

    result = store.observe({**original, "status": "offline"})
    current = next(item for item in store.list_assets() if item["asset_id"] == 19)

    assert result["changed"] is True
    assert current["added_at"] == added["added_at"]
    assert current["last_change_type"] == "status_changed"
