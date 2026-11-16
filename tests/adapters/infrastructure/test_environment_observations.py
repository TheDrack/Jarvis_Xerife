from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.adapters.infrastructure.routers import environment_observations as module
from app.core.nexus import nexus
from fastapi import FastAPI
from fastapi.testclient import TestClient


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, database):
        self.database = database
        self.operation = "select"
        self.payload = None
        self.filters = {}
        self.limit_count = None
        self.order_key = None
        self.descending = False

    def select(self, *_args):
        if self.operation != "insert":
            self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, key, desc=False):
        self.order_key = key
        self.descending = desc
        return self

    def limit(self, count):
        self.limit_count = count
        return self

    def execute(self):
        if self.operation == "insert":
            unique = (self.payload["user_id"], self.payload["request_id"])
            if any(
                (row["user_id"], row["request_id"]) == unique
                for row in self.database.rows
            ):
                raise RuntimeError("unique constraint")
            self.database.rows.append(dict(self.payload))
            return Result([dict(self.payload)])
        rows = [
            dict(row)
            for row in self.database.rows
            if all(row.get(key) == value for key, value in self.filters.items())
        ]
        if self.order_key:
            rows.sort(
                key=lambda row: row.get(self.order_key, ""), reverse=self.descending
            )
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return Result(rows)


class Database:
    def __init__(self):
        self.rows = []

    def table(self, name):
        assert name == module.TABLE
        return Query(self)


class Auth:
    def verify_token(self, token):
        if token != "valid":
            return None
        return {
            "sub": "user@example.test",
            "user_id": "user-1",
            **self.extra_claims,
        }


def make_client(monkeypatch, database=None, claims=None):
    auth = Auth()
    auth.extra_claims = claims or {}
    monkeypatch.setattr(
        nexus, "resolve", lambda name: auth if name == "auth_adapter" else None
    )
    monkeypatch.setattr(module, "get_supabase_admin_client", lambda: database)

    async def current_user():
        return SimpleNamespace(username="user@example.test", user_id="user-1")

    app = FastAPI()
    app.include_router(module.create_environment_observations_router(current_user))
    return TestClient(app)


def observation(**overrides):
    body = {
        "device_id": "desktop-main",
        "source_device_type": "desktop",
        "observation_type": "network_snapshot",
        "schema_version": 1,
        "request_id": str(uuid4()),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"interfaces": [], "neighbors": [], "platform": "windows"},
    }
    body.update(overrides)
    return body


def test_ingest_requires_bearer_even_if_user_dependency_is_present(monkeypatch):
    client = make_client(monkeypatch, Database())
    response = client.post("/v1/environment/observations", json=observation())
    assert response.status_code == 401


def test_ingest_derives_owner_from_verified_identity_and_is_idempotent(monkeypatch):
    database = Database()
    client = make_client(monkeypatch, database)
    body = observation()
    first = client.post(
        "/v1/environment/observations",
        json=body,
        headers={"Authorization": "Bearer valid"},
    )
    second = client.post(
        "/v1/environment/observations",
        json=body,
        headers={"Authorization": "Bearer valid"},
    )
    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    assert len(database.rows) == 1
    assert database.rows[0]["user_id"] == "user-1"


def test_ingest_rejects_client_supplied_owner(monkeypatch):
    client = make_client(monkeypatch, Database())
    body = observation(user_id="another-user")
    response = client.post(
        "/v1/environment/observations",
        json=body,
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 422


def test_mobile_token_must_be_bound_to_submitted_device(monkeypatch):
    client = make_client(
        monkeypatch, Database(), {"client": "jarvis-mobile", "device_id": "phone-1"}
    )
    body = observation(device_id="phone-2", source_device_type="mobile")
    response = client.post(
        "/v1/environment/observations",
        json=body,
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 403


def test_mobile_token_cannot_publish_desktop_observation(monkeypatch):
    client = make_client(
        monkeypatch, Database(), {"client": "jarvis-mobile", "device_id": "phone-1"}
    )
    body = observation(device_id="phone-1")
    response = client.post(
        "/v1/environment/observations",
        json=body,
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 403


def test_ingest_rejects_future_timestamp_and_sensitive_payload_keys(monkeypatch):
    client = make_client(monkeypatch, Database())
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    response = client.post(
        "/v1/environment/observations",
        json=observation(observed_at=future.isoformat()),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 422
    response = client.post(
        "/v1/environment/observations",
        json=observation(payload={"ssid": "private-network"}),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 422


def test_latest_returns_only_current_users_latest_records_with_freshness(monkeypatch):
    database = Database()
    now = datetime.now(timezone.utc)
    database.rows.extend(
        [
            {
                "user_id": "user-1",
                "device_id": "desktop-main",
                "source_device_type": "desktop",
                "observation_type": "network_snapshot",
                "schema_version": 1,
                "observed_at": now.isoformat(),
                "received_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
                "payload": {"interfaces": []},
                "request_id": str(uuid4()),
            },
            {
                "user_id": "user-1",
                "device_id": "phone-1",
                "source_device_type": "mobile",
                "observation_type": "network_snapshot",
                "schema_version": 1,
                "observed_at": now.isoformat(),
                "received_at": now.isoformat(),
                "expires_at": (now - timedelta(minutes=1)).isoformat(),
                "payload": {"network_type": "wifi"},
                "request_id": str(uuid4()),
            },
            {
                "user_id": "other-user",
                "device_id": "foreign",
                "source_device_type": "desktop",
                "observation_type": "network_snapshot",
                "schema_version": 1,
                "observed_at": now.isoformat(),
                "received_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
                "payload": {},
                "request_id": str(uuid4()),
            },
        ]
    )
    client = make_client(monkeypatch, database)
    response = client.get(
        "/v1/environment/observations/latest", headers={"Authorization": "Bearer valid"}
    )
    assert response.status_code == 200
    items = response.json()["observations"]
    assert {item["device_id"] for item in items} == {"desktop-main", "phone-1"}
    freshness = {item["device_id"]: item["freshness"] for item in items}
    assert freshness == {"desktop-main": "fresh", "phone-1": "stale"}


def test_storage_unavailable_fails_closed(monkeypatch):
    client = make_client(monkeypatch, None)
    response = client.post(
        "/v1/environment/observations",
        json=observation(),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 503


def test_api_server_registers_authenticated_observation_router():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    api = (root / "app" / "adapters" / "infrastructure" / "api_server.py").read_text(
        encoding="utf-8"
    )
    assert "create_environment_observations_router" in api
    assert (
        "app.include_router(create_environment_observations_router(get_current_user))"
        in api
    )


def test_baseline_migration_defines_observation_schema_and_enables_rls():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    migration = (
        root / "supabase" / "migrations" / "20261029110505_environment_observations.sql"
    ).read_text(encoding="utf-8")
    assert "enable row level security" in migration.lower()
    assert "unique (user_id, request_id)" in migration.lower()
    assert "constraint jarvis_environment_observations_expiry" in migration.lower()


def test_payload_size_is_bounded(monkeypatch):
    client = make_client(monkeypatch, Database())
    response = client.post(
        "/v1/environment/observations",
        json=observation(payload={"blob": "x" * (33 * 1024)}),
        headers={"Authorization": "Bearer valid"},
    )
    assert response.status_code == 422


def test_follow_up_migration_revokes_unneeded_server_privileges():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    migration = (
        (
            root
            / "supabase"
            / "migrations"
            / "20261029112400_environment_observations_least_privilege.sql"
        )
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "revoke all on table public.jarvis_environment_observations" in migration
    assert "from public, anon, authenticated, service_role" in migration
    assert (
        "grant select, insert on table public.jarvis_environment_observations to service_role"
        in migration
    )


def test_location_snapshot_requires_mobile_opt_in_and_valid_coordinates():
    valid = observation(
        source_device_type="mobile",
        observation_type="location_snapshot",
        payload={
            "location_opt_in": True,
            "location": {"latitude": -27.5, "longitude": -48.5, "accuracy_m": 12.0},
        },
    )
    module.EnvironmentObservationCreate(**valid)
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(**dict(valid, source_device_type="desktop"))
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(valid, payload={"location": {"latitude": -27.5, "longitude": -48.5}})
        )
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(
                valid,
                payload={
                    "location_opt_in": True,
                    "location": {"latitude": 91, "longitude": -48.5},
                },
            )
        )


def test_expired_location_snapshot_hides_coordinates():
    now = datetime.now(timezone.utc)
    row = {
        "device_id": "phone-1",
        "source_device_type": "mobile",
        "observation_type": "location_snapshot",
        "observed_at": now.isoformat(),
        "received_at": (now - timedelta(minutes=3)).isoformat(),
        "expires_at": (now - timedelta(minutes=1)).isoformat(),
        "payload": {
            "location_opt_in": True,
            "location": {"latitude": -27.5, "longitude": -48.5},
        },
    }
    result = module._public_observation(row, now)
    assert result["freshness"] == "stale"
    assert result["payload"] == {}


def test_app_usage_snapshot_requires_mobile_explicit_usage_access_consent():
    valid = observation(
        device_id="phone-1",
        source_device_type="mobile",
        observation_type="app_usage_snapshot",
        payload={
            "platform": "android",
            "usage_access_opt_in": True,
            "collection_status": "ok",
            "window_start": (
                datetime.now(timezone.utc) - timedelta(minutes=60)
            ).isoformat(),
            "window_end": datetime.now(timezone.utc).isoformat(),
            "apps": [
                {
                    "uid": 10123,
                    "package_names": ["com.example.app"],
                    "wifi": {"rx_bytes": 100, "tx_bytes": 50},
                    "mobile": {"rx_bytes": 20, "tx_bytes": 10},
                }
            ],
        },
    )
    module.EnvironmentObservationCreate(**valid)
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(**dict(valid, source_device_type="desktop"))
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(valid, payload={**valid["payload"], "usage_access_opt_in": False})
        )


def test_network_snapshot_validates_nonnegative_vpn_tunnel_counters():
    payload = {
        "platform": "android",
        "vpn_tunnel_stats": {
            "tx_packets": 10,
            "tx_bytes": 2048,
            "rx_packets": 12,
            "rx_bytes": 4096,
        },
    }
    valid = observation(
        device_id="phone-1",
        source_device_type="mobile",
        observation_type="network_snapshot",
        payload=payload,
    )
    module.EnvironmentObservationCreate(**valid)

    for invalid_value in (-1, True, 1.5, "10"):
        invalid_payload = {
            **payload,
            "vpn_tunnel_stats": {**payload["vpn_tunnel_stats"], "tx_bytes": invalid_value},
        }
        with pytest.raises(ValueError):
            module.EnvironmentObservationCreate(**dict(valid, payload=invalid_payload))


def test_network_snapshot_accepts_bounded_per_flow_uid_attribution():
    now = datetime.now(timezone.utc)
    flow = {
        "flow_id": str(uuid4()),
        "protocol": "tcp",
        "local_ip": "10.0.0.2",
        "local_port": 49152,
        "remote_ip": "1.1.1.1",
        "remote_port": 443,
        "uid": 10123,
        "package_names": ["com.example.app"],
        "app_label": "Example",
        "attribution_status": "resolved",
        "first_seen_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "tx_packets": 1,
        "tx_bytes": 60,
        "rx_packets": 2,
        "rx_bytes": 104,
        "closed": False,
    }
    valid = observation(
        device_id="phone-1",
        source_device_type="mobile",
        observation_type="network_snapshot",
        payload={"platform": "android", "flow_metadata_opt_in": True, "flows": [flow]},
    )
    module.EnvironmentObservationCreate(**valid)

    zero_port_flow = {**flow, "flow_id": str(uuid4()), "local_port": 0}
    module.EnvironmentObservationCreate(
        **dict(
            valid,
            payload={
                "platform": "android",
                "flow_metadata_opt_in": True,
                "flows": [zero_port_flow],
            },
        )
    )

    shared_uid_flow = {
        **flow,
        "flow_id": str(uuid4()),
        "package_names": ["com.example.first", "com.example.second"],
        "app_label": None,
        "attribution_status": "shared_uid",
    }
    module.EnvironmentObservationCreate(
        **dict(
            valid,
            payload={
                "platform": "android",
                "flow_metadata_opt_in": True,
                "flows": [shared_uid_flow],
            },
        )
    )

    invalid_flows = [
        {**flow, "local_ip": "not-an-ip"},
        {**flow, "local_port": 65536},
        {**flow, "uid": True},
        {**flow, "tx_bytes": -1},
        {**flow, "closed": 1},
        {**flow, "attribution_status": "resolved", "uid": None},
        {**flow, "attribution_status": "unresolved", "uid": 10123},
    ]
    for invalid_flow in invalid_flows:
        with pytest.raises(ValueError):
            module.EnvironmentObservationCreate(
                **dict(valid, payload={"platform": "android", "flow_metadata_opt_in": True, "flows": [invalid_flow]})
            )

    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(valid, payload={"platform": "android", "flow_metadata_opt_in": False, "flows": [flow]})
        )

    duplicate = {**flow}
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(valid, payload={"platform": "android", "flow_metadata_opt_in": True, "flows": [flow, duplicate]})
        )

    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(valid, payload={"platform": "android", "flow_metadata_opt_in": True, "flows": [flow] * 51})
        )


def test_flow_metadata_is_restricted_to_mobile_network_snapshots():
    body = observation(
        device_id="phone-1",
        source_device_type="mobile",
        observation_type="network_snapshot",
        payload={"flow_metadata_opt_in": True, "flows": []},
    )

    with pytest.raises(ValueError, match="flow metadata is only valid"):
        module.EnvironmentObservationCreate(
            **dict(body, source_device_type="desktop")
        )

    with pytest.raises(ValueError, match="flow metadata is only valid"):
        module.EnvironmentObservationCreate(
            **dict(body, observation_type="presence")
        )

    with pytest.raises(ValueError, match="flow metadata is only valid"):
        module.EnvironmentObservationCreate(
            **dict(body, observation_type="app_usage_snapshot")
        )


def test_network_payload_metadata_requires_separate_mobile_opt_in():
    now = datetime.now(timezone.utc)
    flow = {
        "flow_id": str(uuid4()),
        "protocol": "tcp",
        "local_ip": "10.0.0.2",
        "local_port": 49152,
        "remote_ip": "1.1.1.1",
        "remote_port": 443,
        "uid": 10123,
        "package_names": ["com.example.app"],
        "app_label": "Example",
        "attribution_status": "resolved",
        "first_seen_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "tx_packets": 1,
        "tx_bytes": 60,
        "rx_packets": 1,
        "rx_bytes": 52,
        "closed": False,
        "protocol_observations": [
            {"kind": "tls_sni", "value": "api.example.com", "source": "tls_client_hello"},
            {"kind": "dns_query", "value": "api.example.com", "source": "dns"},
        ],
    }
    body = observation(
        device_id="phone-1",
        source_device_type="mobile",
        observation_type="network_snapshot",
        payload={
            "platform": "android",
            "flow_metadata_opt_in": True,
            "payload_metadata_opt_in": True,
            "flows": [flow],
        },
    )
    module.EnvironmentObservationCreate(**body)

    with pytest.raises(ValueError, match="payload metadata requires"):
        module.EnvironmentObservationCreate(
            **dict(body, payload={"platform": "android", "flow_metadata_opt_in": True, "flows": [flow]})
        )

    with pytest.raises(ValueError, match="protocol observations require"):
        module.EnvironmentObservationCreate(
            **dict(
                body,
                payload={
                    "platform": "android",
                    "flow_metadata_opt_in": True,
                    "payload_metadata_opt_in": False,
                    "flows": [flow],
                },
            )
        )

    invalid_observation = {
        "kind": "http_host",
        "value": "https://example.com/private",
        "source": "http",
    }
    with pytest.raises(ValueError, match="protocol observation"):
        module.EnvironmentObservationCreate(
            **dict(
                body,
                payload={
                    **body["payload"],
                    "flows": [{**flow, "protocol_observations": [invalid_observation]}],
                },
            )
        )

    invalid_kind = {"kind": [], "value": "api.example.com", "source": "dns"}
    with pytest.raises(ValueError, match="protocol observation kind/source"):
        module.EnvironmentObservationCreate(
            **dict(
                body,
                payload={
                    **body["payload"],
                    "flows": [{**flow, "protocol_observations": [invalid_kind]}],
                },
            )
        )

    with pytest.raises(ValueError, match="payload metadata is only valid"):
        module.EnvironmentObservationCreate(
            **dict(body, source_device_type="desktop")
        )


def test_app_usage_snapshot_accepts_bounded_package_identity_metadata():
    now = datetime.now(timezone.utc)
    valid = observation(
        device_id="phone-1",
        source_device_type="mobile",
        observation_type="app_usage_snapshot",
        payload={
            "platform": "android",
            "usage_access_opt_in": True,
            "collection_status": "ok",
            "window_start": (now - timedelta(minutes=60)).isoformat(),
            "window_end": now.isoformat(),
            "apps": [{
                "uid": 10123,
                "package_names": ["com.example.app"],
                "packages": [{
                    "package_name": "com.example.app",
                    "app_label": "Example",
                    "is_system_app": False,
                }],
                "wifi": {"rx_bytes": 100, "tx_bytes": 50},
                "mobile": {"rx_bytes": 20, "tx_bytes": 10},
            }],
        },
    )
    module.EnvironmentObservationCreate(**valid)
    invalid_payload = {**valid["payload"], "apps": [{
        **valid["payload"]["apps"][0],
        "packages": [{"package_name": "com.example.app", "app_label": "x" * 129, "is_system_app": False}],
    }]}
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(**dict(valid, payload=invalid_payload))


def test_app_usage_snapshot_rejects_unbounded_or_invalid_uid_counters():
    base_payload = {
        "platform": "android",
        "usage_access_opt_in": True,
        "collection_status": "ok",
        "window_start": (
            datetime.now(timezone.utc) - timedelta(minutes=60)
        ).isoformat(),
        "window_end": datetime.now(timezone.utc).isoformat(),
        "apps": [
            {
                "uid": 10123,
                "package_names": [],
                "wifi": {"rx_bytes": 0, "tx_bytes": 0},
                "mobile": {"rx_bytes": 0, "tx_bytes": 0},
            }
        ],
    }
    body = observation(
        device_id="phone-1",
        source_device_type="mobile",
        observation_type="app_usage_snapshot",
        payload=base_payload,
    )
    module.EnvironmentObservationCreate(**body)
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(
                body,
                payload={
                    **base_payload,
                    "apps": [
                        {
                            "uid": -1,
                            "package_names": [],
                            "wifi": {"rx_bytes": 0, "tx_bytes": 0},
                            "mobile": {"rx_bytes": 0, "tx_bytes": 0},
                        }
                    ],
                },
            )
        )
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(
                body,
                payload={
                    **base_payload,
                    "apps": [
                        {
                            "uid": 10123,
                            "package_names": [],
                            "wifi": {"rx_bytes": -1, "tx_bytes": 0},
                            "mobile": {"rx_bytes": 0, "tx_bytes": 0},
                        }
                    ],
                },
            )
        )
    with pytest.raises(ValueError):
        module.EnvironmentObservationCreate(
            **dict(body, payload={**base_payload, "apps": [{}] * 51})
        )


def test_forward_migration_allows_location_and_app_usage_observation_types():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    migration = (
        (
            root
            / "supabase"
            / "migrations"
            / "20261116090000_app_usage_observation_type.sql"
        )
        .read_text(encoding="utf-8")
        .lower()
    )
    assert "location_snapshot" in migration
    assert "app_usage_snapshot" in migration
