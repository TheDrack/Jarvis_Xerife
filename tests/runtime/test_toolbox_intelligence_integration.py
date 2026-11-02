from datetime import datetime, timedelta, timezone

import httpx

from app.core.nexus import nexus
from app.runtime.toolbox import ToolAuthorizationDecision, ToolDispatcher, ToolRegistry


class TestReadOnlyPolicy:
    def authorize_tool(self, request, manifest):
        return ToolAuthorizationDecision(
            granted=True,
            principal_id="integration-test",
            session_id="integration-session",
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            capability=request.capability or manifest.capabilities[0],
            scope=request.scope,
            operation=manifest.operation,
            approval_id=request.approval_id,
            correlation_id=request.correlation_id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )


def test_public_intelligence_dispatch_resolves_nexus_adapter_end_to_end():
    def respond(request):
        if request.url.host == "api.gdeltproject.org":
            return httpx.Response(
                200,
                json={
                    "articles": [
                        {
                            "url": "https://news.example/article",
                            "title": "AI research update",
                            "seendate": "20261102T120000Z",
                            "domain": "news.example",
                        }
                    ]
                },
            )
        if request.url.host == "eonet.gsfc.nasa.gov":
            return httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "id": "EONET_TEST_1",
                            "title": "Wildfire event",
                            "geometry": [
                                {
                                    "date": "2026-11-02T10:00:00Z",
                                    "coordinates": [-70.0, -10.0],
                                }
                            ],
                            "sources": [{"url": "https://example.org/event"}],
                            "categories": [{"title": "Wildfires"}],
                        }
                    ]
                },
            )
        if request.url.host == "earthquake.usgs.gov":
            return httpx.Response(
                200,
                json={
                    "features": [
                        {
                            "id": "usgs-test-1",
                            "properties": {
                                "title": "M 4.2 - Test region",
                                "time": 1793620800000,
                                "url": "https://earthquake.usgs.gov/test",
                                "mag": 4.2,
                            },
                            "geometry": {"coordinates": [-71.0, -11.0, 10.0]},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    adapter = nexus.resolve("public_intelligence_adapter", use_cache=False)
    assert adapter is not None
    assert getattr(adapter, "__is_cloud_mock__", False) is False
    adapter._client = httpx.Client(transport=httpx.MockTransport(respond))

    try:
        dispatcher = ToolDispatcher(
            ToolRegistry.from_file(),
            authorizer=TestReadOnlyPolicy(),
        )
        result = dispatcher.dispatch(
            {
                "tool_id": "intelligence.snapshot.collect",
                "arguments": {"limit": 5},
                "scope": "local",
            }
        )
    finally:
        adapter.close()

    assert result.success is True
    assert len(result.output["events"]) == 3
    assert {source["source_id"] for source in result.output["sources"]} == {
        "gdelt",
        "nasa_eonet",
        "usgs_earthquakes",
    }
    assert all(source["available"] for source in result.output["sources"])
    assert {event["source_id"] for event in result.output["events"]} == {
        "gdelt",
        "nasa_eonet",
        "usgs_earthquakes",
    }
