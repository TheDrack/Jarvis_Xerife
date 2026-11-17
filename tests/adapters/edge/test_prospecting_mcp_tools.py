from app.adapters.edge import prospecting_mcp_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, name):
        def register(function):
            self.tools[name] = function
            return function
        return register


class FakeAdapter:
    def __init__(self, *, available=True):
        self.available = available

    def can_execute(self, context=None):
        return self.available

    def search_companies(self, **kwargs):
        return {"success": True, "received": kwargs}

    def lookup_company(self, cnpj):
        return {"success": True, "found": cnpj == "12345678000190"}


def test_registers_search_and_exact_cnpj_lookup_tools(monkeypatch):
    mcp = FakeMCP()
    adapter = FakeAdapter()
    monkeypatch.setattr(prospecting_mcp_tools.nexus, "resolve", lambda component_id: adapter)

    names = prospecting_mcp_tools.register_prospecting_tools(mcp)
    search = mcp.tools["prospecting.companies.search"]
    lookup = mcp.tools["prospecting.companies.lookup"]

    result = search(
        uf="SC",
        cnae_prefixes=["4120"],
        municipalities=["São José"],
        limit=25,
    )
    found = lookup(cnpj="12345678000190")

    assert names == ("prospecting.companies.search", "prospecting.companies.lookup")
    assert result["success"] is True
    assert result["received"]["uf"] == "SC"
    assert result["received"]["limit"] == 25
    assert found == {"success": True, "found": True}


def test_mcp_search_reports_missing_store_without_exposing_host_paths(monkeypatch):
    mcp = FakeMCP()
    adapter = FakeAdapter(available=False)
    monkeypatch.setattr(prospecting_mcp_tools.nexus, "resolve", lambda component_id: adapter)

    prospecting_mcp_tools.register_prospecting_tools(mcp)
    result = mcp.tools["prospecting.companies.search"](
        uf="SC",
        cnae_prefixes=["41"],
    )

    assert result["success"] is False
    assert result["error_code"] == "prospecting_store_unavailable"
    assert "CNPJ DuckDB store" in result["message"]
    assert "C:\\" not in result["message"]
