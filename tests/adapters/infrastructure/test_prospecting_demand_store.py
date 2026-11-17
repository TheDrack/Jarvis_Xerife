from uuid import uuid4

import pytest

from app.adapters.infrastructure.prospecting.demand_store import (
    DemandNotFound,
    SQLiteDemandStore,
)
from app.domain.prospecting.demand import DemandIntent, DemandRequest, MarketDirection, RequesterType


def make_demand(tenant_id, requester_id="user-1"):
    return DemandRequest(
        tenant_id=tenant_id,
        requester_id=requester_id,
        requester_type=RequesterType.INDIVIDUAL,
        direction=MarketDirection.B2C,
        intent=DemandIntent.FIND_SUPPLIERS,
        title="Find a local supplier",
        description="Need a local supplier for a custom metal gate.",
        categories=("serralheria",),
        city="São José",
        state="SC",
    )


def test_demand_store_round_trips_and_isolates_tenants(tmp_path):
    store = SQLiteDemandStore(tmp_path / "demands.sqlite3")
    tenant = uuid4()
    demand = make_demand(tenant)
    store.create(demand)

    assert store.get(demand.demand_id, tenant_id=tenant) == demand
    assert store.list_for_requester("user-1", tenant_id=tenant) == (demand,)
    with pytest.raises(DemandNotFound):
        store.get(demand.demand_id, tenant_id=uuid4())


def test_demand_store_lists_only_requesters_within_tenant(tmp_path):
    store = SQLiteDemandStore(tmp_path / "demands.sqlite3")
    tenant = uuid4()
    first = make_demand(tenant, "user-1")
    second = make_demand(tenant, "user-2")
    store.create(first)
    store.create(second)

    assert store.list_for_requester("user-1", tenant_id=tenant) == (first,)


def test_demand_store_rejects_unbounded_list_limit(tmp_path):
    store = SQLiteDemandStore(tmp_path / "demands.sqlite3")
    with pytest.raises(ValueError, match="demand_list_limit_out_of_range"):
        store.list_for_requester("user-1", tenant_id=uuid4(), limit=10000)


def test_profile_consent_can_be_withdrawn_and_is_audited(tmp_path):
    from datetime import datetime, timezone
    from app.domain.prospecting.demand import DemandIntent, DemandRequest, MarketDirection, RequesterType

    store = SQLiteDemandStore(tmp_path / "demands.sqlite3")
    tenant = uuid4()
    demand = DemandRequest(
        tenant_id=tenant,
        requester_id="user-1",
        requester_type=RequesterType.INDIVIDUAL,
        direction=MarketDirection.C2B,
        intent=DemandIntent.FIND_JOBS,
        title="Python backend role",
        description="Looking for Python backend engineering work.",
        categories=("python", "backend"),
        profile_reference="vault://cv/123",
        consent_to_share_profile=True,
        consent_recorded_at=datetime.now(timezone.utc),
        consent_scope="Only employer for vacancy 42",
    )
    store.create(demand)

    withdrawn = store.withdraw_profile_consent(
        demand.demand_id, tenant_id=tenant, requester_id="user-1",
    )

    assert withdrawn.consent_to_share_profile is False
    assert withdrawn.profile_reference is None
    assert withdrawn.consent_recorded_at is None
    assert store.get(demand.demand_id, tenant_id=tenant) == withdrawn
    events = store.list_events(demand.demand_id, tenant_id=tenant)
    assert [event["event_type"] for event in events] == [
        "demand_created", "profile_sharing_withdrawn",
    ]
