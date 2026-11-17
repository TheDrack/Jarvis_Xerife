from types import SimpleNamespace

import pytest

from app.adapters.edge import prospecting_mcp_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, name):
        def register(function):
            self.tools[name] = function
            return function
        return register


class FakeDispatcher:
    def __init__(self, *, success=True, output=None, error_code=None):
        self.requests = []
        self.success = success
        self.output = output or {"success": True, "companies": []}
        self.error_code = error_code

    async def dispatch_async(self, request):
        self.requests.append(request)
        return SimpleNamespace(
            success=self.success,
            output=self.output,
            error_code=self.error_code,
            retryable=False,
            retry_after_seconds=None,
        )


@pytest.mark.asyncio
async def test_registers_search_and_exact_cnpj_lookup_through_tool_dispatcher():
    mcp = FakeMCP()
    dispatcher = FakeDispatcher(output={"success": True, "companies": [{"cnpj": "12345678000190"}]})

    names = prospecting_mcp_tools.register_prospecting_tools(mcp, dispatcher=dispatcher)
    search = await mcp.tools["prospecting.companies.search"](
        uf="SC",
        cnae_prefixes=["4120"],
        municipalities=["São José"],
        limit=25,
    )
    lookup = await mcp.tools["prospecting.companies.lookup"](
        cnpj="12345678000190"
    )

    assert names == ("prospecting.companies.search", "prospecting.companies.lookup")
    assert search["companies"][0]["cnpj"] == "12345678000190"
    assert lookup["success"] is True
    assert dispatcher.requests[0]["tool_id"] == "prospecting.companies.search"
    assert dispatcher.requests[0]["capability"] == "prospecting.cnpj.read"
    assert dispatcher.requests[0]["arguments"]["limit"] == 25
    assert dispatcher.requests[0]["scope"] == "local"
    assert dispatcher.requests[1]["tool_id"] == "prospecting.companies.lookup"


@pytest.mark.asyncio
async def test_mcp_search_returns_safe_authorization_failure():
    mcp = FakeMCP()
    dispatcher = FakeDispatcher(success=False, error_code="authorization_denied")

    prospecting_mcp_tools.register_prospecting_tools(mcp, dispatcher=dispatcher)
    result = await mcp.tools["prospecting.companies.search"](
        uf="SC",
        cnae_prefixes=["41"],
    )

    assert result["success"] is False
    assert result["error_code"] == "authorization_denied"
    assert "termux_jarvis" in result["message"]


def test_dispatcher_uses_the_session_gateway_capability(monkeypatch):
    calls = []

    class Gateway:
        def require(self, capability):
            calls.append(capability)
            return {"session_id": "session-1", "capability": capability}

    class FakeRegistry:
        @classmethod
        def from_file(cls):
            return object()

    class FakePolicy:
        def __init__(self, *, principal_resolver):
            self.principal_resolver = principal_resolver

    class FakeDispatcher:
        def __init__(self, registry, *, authorizer, event_sink):
            self.registry = registry
            self.authorizer = authorizer
            self.event_sink = event_sink

    monkeypatch.setattr(prospecting_mcp_tools, "ToolRegistry", FakeRegistry)
    monkeypatch.setattr(prospecting_mcp_tools, "HostToolAuthorizationPolicy", FakePolicy)
    monkeypatch.setattr(prospecting_mcp_tools, "ToolDispatcher", FakeDispatcher)
    monkeypatch.setattr(prospecting_mcp_tools, "JsonlToolAuditSink", lambda: "audit")

    dispatcher = prospecting_mcp_tools._build_dispatcher(session_gateway=Gateway())
    principal = dispatcher.authorizer.principal_resolver()

    assert calls == ["prospecting.cnpj.read"]
    assert principal.principal_id == "local-owner"
    assert principal.capabilities == frozenset({"prospecting.cnpj.read"})


@pytest.mark.asyncio
async def test_search_omits_optional_nulls_before_tool_schema_validation():
    mcp = FakeMCP()
    dispatcher = FakeDispatcher()

    prospecting_mcp_tools.register_prospecting_tools(mcp, dispatcher=dispatcher)
    await mcp.tools["prospecting.companies.search"](
        uf="SC",
        cnae_prefixes=["4120"],
    )

    arguments = dispatcher.requests[0]["arguments"]
    assert "municipalities" not in arguments
    assert "after_cnpj_basico" not in arguments
    assert arguments["limit"] == 50
