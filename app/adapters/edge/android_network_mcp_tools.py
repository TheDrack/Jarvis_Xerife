"""Read-only access to the authenticated Android VPN flow snapshot."""
from __future__ import annotations

import re
from typing import Any

from app.adapters.edge.android_accessibility_client import accessibility_request

_PACKAGE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\Z")


def read_android_network_flows_snapshot(package_filter: str = "") -> dict[str, Any]:
    """Read current in-memory VPN flow metadata from the paired Android app."""
    package_filter = package_filter.strip()
    if package_filter and not _PACKAGE_NAME.fullmatch(package_filter):
        raise ValueError("Invalid Android package name filter")
    result = accessibility_request("/v1/network/flows")
    flows = result.get("flows")
    if not isinstance(flows, list):
        raise RuntimeError("Android network snapshot returned an invalid flows collection")
    if package_filter:
        filtered_flows = [
            flow for flow in flows
            if isinstance(flow, dict)
            and isinstance(flow.get("package_names"), list)
            and package_filter in flow["package_names"]
        ]
        result = {**result, "flows": filtered_flows, "flow_count": len(filtered_flows)}
    return result


def register_android_network_tools(mcp: Any) -> None:
    @mcp.tool()
    def android_network_flows_snapshot(package_filter: str = "") -> dict[str, Any]:
        """Read bounded VPN flows and protocol metadata from the paired Android app.

        Requires Jarvis to own Android's active VPN and flow metadata consent.
        Payload-derived hostnames additionally require the separate protocol metadata consent.
        This tool never returns raw packet bytes or encrypted application content.
        """
        return read_android_network_flows_snapshot(package_filter)
