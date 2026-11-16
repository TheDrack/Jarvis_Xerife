"""MCP tools for inspecting and maintaining the protocol pattern registry."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.adapters.edge.protocol_pattern_registry import ProtocolPatternRegistry

protocol_registry = ProtocolPatternRegistry(
    os.environ.get(
        "JARVIS_PROTOCOL_PATTERN_DIR",
        str(Path.home() / ".jarvis" / "protocol-patterns"),
    )
)


def register_protocol_pattern_tools(
    mcp: Any,
    tracked_action: Any | None = None,
    *,
    include_live_android: bool = False,
) -> None:
    """Register protocol pattern operations on an existing MCP server."""
    if tracked_action is None:
        def tracked_action(_label: str):
            def decorate(function: Any):
                return function
            return decorate

    @mcp.tool()
    @tracked_action("Registrando padrão de protocolo observado")
    def protocol_pattern_record_observation(
        package: str, app_version: str, operation: str, observation: dict[str, Any]
    ) -> dict[str, Any]:
        """Registra somente a estrutura observada; valores e segredos são descartados."""
        return protocol_registry.record_observation(
            package=package,
            app_version=app_version,
            operation=operation,
            observation=observation,
        )

    @mcp.tool()
    @tracked_action("Importando metadados passivos de fluxos Android")
    def protocol_pattern_import_android_flows(
        package: str, app_version: str, flows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Importa hostnames da VPN apenas quando o fluxo identifica um único pacote."""
        result = protocol_registry.record_flow_observations(
            package=package,
            app_version=app_version,
            flows=flows,
        )
        return {"success": True, **result}

    if include_live_android:
        from app.adapters.edge.android_network_mcp_tools import (
            read_android_network_flows_snapshot,
        )

        @mcp.tool()
        @tracked_action("Capturando padrões da VPN Android em tempo real")
        def protocol_pattern_import_live_android_flows(package: str) -> dict[str, Any]:
            """Lê o snapshot atual do Android pareado e importa somente fluxos atribuídos ao pacote.

            O Jarvis precisa possuir a VPN ativa. A versão vem do PackageManager Android;
            se não estiver disponível, o registro recebe app_version=unknown.
            """
            snapshot = read_android_network_flows_snapshot(package)
            capture = {
                "capture_owner": snapshot.get("capture_owner"),
                "capture_reason": snapshot.get("capture_reason"),
                "flow_metadata_opt_in": snapshot.get("flow_metadata_opt_in"),
                "payload_metadata_opt_in": snapshot.get("payload_metadata_opt_in"),
                "flow_count": snapshot.get("flow_count", len(snapshot.get("flows", []))),
            }
            if snapshot.get("capture_owner") != "jarvis":
                return {"success": False, "status": "capture_unavailable", "capture": capture}
            if snapshot.get("flow_metadata_opt_in") is not True:
                return {"success": False, "status": "flow_consent_required", "capture": capture}

            flows = snapshot.get("flows", [])
            matching = [
                flow for flow in flows
                if isinstance(flow, dict)
                and isinstance(flow.get("package_names"), list)
                and package in flow["package_names"]
            ]
            versions = {
                (str(version.get("version_name") or "").strip(), str(version.get("version_code") or "").strip())
                for flow in matching
                if flow.get("attribution_status") == "resolved"
                and flow.get("package_names") == [package]
                for version in (
                    flow.get("package_versions")
                    if isinstance(flow.get("package_versions"), list) else []
                )
                if isinstance(version, dict) and version.get("package_name") == package
            }
            if len(versions) > 1:
                return {
                    "success": False,
                    "status": "multiple_package_versions_in_snapshot",
                    "capture": capture,
                    "flows_seen": len(matching),
                }
            version_name, version_code = next(iter(versions), ("", ""))
            app_version = (
                f"{version_name}+{version_code}" if version_name and version_code
                else version_name or version_code or "unknown"
            )
            imported = protocol_registry.record_flow_observations(
                package=package,
                app_version=app_version,
                flows=matching,
            )
            observations_seen = sum(
                len(flow.get("protocol_observations", []))
                for flow in matching
                if isinstance(flow.get("protocol_observations", []), list)
            )
            return {
                "success": True,
                "status": "imported" if imported["recorded"] else "no_new_patterns",
                "package": package,
                "app_version": app_version,
                "flows_seen": len(matching),
                "protocol_observations_seen": observations_seen,
                "capture": capture,
                **imported,
            }

    @mcp.tool()
    @tracked_action("Consultando padrões de protocolo")
    def protocol_pattern_list(package: str = "", operation: str = "") -> dict[str, Any]:
        """Lista padrões versionados, filtrando opcionalmente por pacote e operação."""
        records = protocol_registry.list_patterns(
            package=package or None,
            operation=operation or None,
        )
        return {"success": True, "count": len(records), "patterns": records}

    @mcp.tool()
    @tracked_action("Analisando padrões observados de um aplicativo")
    def protocol_pattern_analyze_package(package: str) -> dict[str, Any]:
        """Resume destinos, protocolos, versões e estados já observados para um pacote."""
        records = protocol_registry.list_patterns(package=package)
        network_records = [record for record in records if isinstance(record.get("network_pattern"), dict)]
        hosts = sorted({record["network_pattern"].get("hostname", "") for record in network_records if record["network_pattern"].get("hostname")})
        operations = sorted({str(record.get("operation", "")) for record in network_records})
        versions = sorted({str(record.get("app_version", "unknown")) for record in records})
        statuses: dict[str, int] = {}
        for record in records:
            status = str(record.get("status", "unknown"))
            statuses[status] = statuses.get(status, 0) + 1
        return {
            "success": True,
            "package": package,
            "pattern_count": len(records),
            "network_pattern_count": len(network_records),
            "versions": versions,
            "operations": operations,
            "hosts": hosts,
            "statuses": statuses,
            "patterns": records,
        }

    @mcp.tool()
    @tracked_action("Atualizando estado de validação de padrão")
    def protocol_pattern_transition(
        pattern_id: str, status: str, evidence: str
    ) -> dict[str, Any]:
        """Avança observed → validated → reusable; exige evidência em cada transição."""
        return protocol_registry.transition(pattern_id, status, evidence=evidence)

    @mcp.tool()
    @tracked_action("Comparando versões de protocolo")
    def protocol_pattern_compare_versions(
        package: str, operation: str, older: str, newer: str
    ) -> dict[str, Any]:
        """Compara estruturas observadas entre duas versões do mesmo aplicativo."""
        return protocol_registry.compare_versions(
            package=package,
            operation=operation,
            older=older,
            newer=newer,
        )
