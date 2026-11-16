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


def register_protocol_pattern_tools(mcp: Any, tracked_action: Any) -> None:
    """Register protocol pattern operations on an existing MCP server."""

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
