from app.adapters.edge.communication_mcp_tools import register_communication_tools
from app.communication import CommunicationRegistry


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, name=None, **_options):
        def decorator(function):
            self.tools[name or function.__name__] = function
            return function

        return decorator


class FakeAdapter:
    adapter_id = "example.http"
    protocol = "https"
    operations = ("get_status", "send_message")

    def execute(self, operation, payload, *, context):
        raise NotImplementedError


def test_communication_mcp_lists_only_registered_adapter_metadata():
    registry = CommunicationRegistry([FakeAdapter()])
    mcp = FakeMCP()
    registered = register_communication_tools(mcp, registry)
    assert registered == ("communication_adapters_list",)
    assert mcp.tools["communication_adapters_list"]() == {
        "success": True,
        "adapters": [
            {
                "adapter_id": "example.http",
                "protocol": "https",
                "operations": ["get_status", "send_message"],
            }
        ],
    }
