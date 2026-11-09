"""Bounded, read-only host resource diagnostics for MCP and other edge runtimes."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.adapters.edge.host.psutil_host_adapter import PsutilHostAdapter
from app.domain.ports.host_port import HostPort


def collect_host_resource_diagnostics(
    adapter: HostPort | None = None,
    *,
    process_limit: int = 25,
    include_storage_inventory: bool = False,
) -> dict[str, Any]:
    """Collect identity, CPU/RAM, mounted disk usage and top processes.

    The host contract intentionally excludes command lines and environment data.
    The limit is stricter than the generic HostPort maximum to keep MCP payloads
    small and predictable.
    """
    if isinstance(process_limit, bool) or not isinstance(process_limit, int):
        raise TypeError("process_limit must be an integer")
    if not 1 <= process_limit <= 50:
        raise ValueError("process_limit must be between 1 and 50")

    if not isinstance(include_storage_inventory, bool):
        raise TypeError("include_storage_inventory must be a boolean")

    host = adapter or PsutilHostAdapter()
    identity = asdict(host.get_identity())
    resources = asdict(host.get_resources())
    resources["captured_at"] = resources["captured_at"].isoformat()
    processes = [asdict(item) for item in host.list_processes(process_limit)]
    memory_method = getattr(host, "list_processes_by_memory", None)
    memory_processes = (
        [asdict(item) for item in memory_method(process_limit)]
        if callable(memory_method)
        else sorted(
            processes,
            key=lambda item: (item["memory_rss_bytes"], item["cpu_percent"], -item["pid"]),
            reverse=True,
        )
    )

    result = {
        "success": True,
        "read_only": True,
        "identity": identity,
        "resources": resources,
        "top_processes": processes,
        "top_cpu_processes": processes,
        "top_memory_processes": memory_processes,
        "process_limit": process_limit,
        "privacy": {
            "command_lines_collected": False,
            "environment_variables_collected": False,
            "file_contents_collected": False,
        },
    }

    if include_storage_inventory:
        from app.adapters.edge.host_storage_diagnostics import collect_host_storage_diagnostics

        result["storage_inventory"] = collect_host_storage_diagnostics()
    result["storage_inventory_included"] = include_storage_inventory
    return result
