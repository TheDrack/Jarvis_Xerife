from types import SimpleNamespace
from uuid import UUID

from app.adapters.edge import prospecting_demand_mcp_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, name):
        def register(function):
            self.tools[name] = function
            return function
        return register


class FakeGateway:
    def __init__(self):
        self.calls = []

    def require(self, capability):
        self.calls.append(capability)
        return {"session_id": "session-123"}


class FakeStore:
    def __init__(self):
        self.rows = {}

    def create(self, demand):
        self.rows[str(demand.demand_id)] = demand

    def get(self, demand_id, *, tenant_id):
        demand = self.rows[str(demand_id)]
        assert demand.tenant_id == tenant_id
        return demand

    def list_for_requester(self, requester_id, *, tenant_id, limit):
        return tuple(
            row for row in self.rows.values()
            if row.requester_id == requester_id and row.tenant_id == tenant_id
        )[:limit]


def test_demand_mcp_creates_and_retrieves_private_b2c_supplier_request():
    mcp, gateway, store = FakeMCP(), FakeGateway(), FakeStore()
    names = prospecting_demand_mcp_tools.register_prospecting_demand_tools(
        mcp, store=store, session_gateway=gateway,
    )
    created = mcp.tools["prospecting.demands.create"](
        requester_type="individual",
        direction="b2c",
        intent="find_suppliers",
        title="Find a local metalworker",
        description="Need a local supplier for a custom metal gate.",
        categories=["serralheria"],
        city="São José",
        state="SC",
    )
    demand_id = created["demand_id"]
    retrieved = mcp.tools["prospecting.demands.get"](demand_id=demand_id)
    listed = mcp.tools["prospecting.demands.list"](limit=10)

    assert names == (
        "prospecting.demands.create",
        "prospecting.demands.get",
        "prospecting.demands.list",
    )
    assert created["success"] is True
    assert retrieved["demand"]["direction"] == "b2c"
    assert listed["count"] == 1
    assert gateway.calls == ["prospecting.demand.manage"] * 3


def test_job_request_cannot_enable_cv_sharing_without_reference_and_scope():
    mcp = FakeMCP()
    prospecting_demand_mcp_tools.register_prospecting_demand_tools(
        mcp, store=FakeStore(), session_gateway=FakeGateway(),
    )
    result = mcp.tools["prospecting.demands.create"](
        requester_type="individual",
        direction="c2b",
        intent="find_jobs",
        title="Python backend role",
        description="Looking for Python backend engineering work.",
        categories=["python", "backend"],
        consent_to_share_profile=True,
    )
    assert result["success"] is False
    assert "profile_sharing_requires_explicit_scoped_consent" in result["error_code"]
