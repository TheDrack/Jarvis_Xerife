"""Authenticated status API and permanent UI for Jarvis Universal Intelligence."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse


def _configured(variable: str) -> bool:
    return bool(os.getenv(variable, "").strip())


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_intelligence_status() -> dict[str, Any]:
    """Return only verifiable configuration/implementation state, never fabricated telemetry."""
    root = _repository_root()
    migration = root / "supabase" / "migrations" / "20261103100304_intelligence_history.sql"
    migration_present = migration.is_file()
    adapter_present = (root / "app" / "adapters" / "infrastructure" / "intelligence" / "supabase_intelligence_history_adapter.py").is_file()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": "partial",
        "data_plane": {
            "available": False,
            "reason": "collection_runtime_not_connected",
            "event_count": None,
            "observation_count": None,
            "last_collection_at": None,
        },
        "sources": [
            {
                "id": "public_intelligence",
                "label": "Public Intelligence",
                "implementation": "implemented",
                "runtime": "not_scheduled",
                "details": "GDELT, NASA EONET e USGS; coleta ainda não conectada ao runtime.",
            },
            {
                "id": "gods_eye_view",
                "label": "God's Eye View",
                "implementation": "implemented",
                "runtime": (
                    "configured_not_probed"
                    if _configured("JARVIS_GEV_MCP_ENTRYPOINT")
                    else "not_configured"
                ),
                "details": "Adaptador MCP local, allowlist read-only; configuração não comprova conectividade.",
            },
            {
                "id": "osiris",
                "label": "OSIRIS",
                "implementation": "implemented",
                "runtime": (
                    "configured_not_probed"
                    if _configured("JARVIS_OSIRIS_API_BASE_URL")
                    else "not_configured"
                ),
                "details": "Adaptador REST HTTPS read-only; endpoint configurado não comprova saúde.",
            },
        ],
        "pipeline": [
            {
                "id": "sources",
                "label": "Adaptadores de origem",
                "state": "implemented",
                "detail": "Contratos e adaptadores com testes unitários.",
            },
            {
                "id": "normalization",
                "label": "Normalização e síntese",
                "state": "implemented",
                "detail": "IntelligenceCore determinístico; ainda sem coleta agendada.",
            },
            {
                "id": "durable_history",
                "label": "Schema de histórico",
                "state": "migration_defined" if migration_present else "unknown",
                "detail": "Migration versionada no repositório; aplicação remota não verificada.",
            },
            {
                "id": "persistence_adapter",
                "label": "Adaptador de persistência",
                "state": "implemented_not_connected",
                "detail": "Adaptador append-only disponível; ainda não conectado ao coletor e exige cliente admin server-side.",
            },
            {
                "id": "presentation",
                "label": "Apresentação e histórico",
                "state": "in_progress",
                "detail": "Painel de acompanhamento implementado; feed e mapa dependem do coletor real.",
            },
        ],
        "history": {
            "migration_file_present": migration_present,
            "remote_migration_state": "unverified",
            "persistence_adapter": "implemented" if adapter_present else "not_implemented",
            "production_write_performed": False,
        },
        "security": {
            "status_endpoint_authenticated": True,
            "source_adapters_read_only": True,
            "browser_receives_provider_credentials": False,
        },
        "limitations": [
            "Sem serviço de coleta conectado, eventos e observações não estão disponíveis nesta tela.",
            "Estado de configuração não equivale a health check do serviço externo.",
            "O estado remoto da migration do Supabase não é consultado por este endpoint.",
            "O adaptador de histórico ainda não está conectado ao endpoint de coleta.",
        ],
    }


def create_intelligence_dashboard_router(get_current_user) -> APIRouter:
    router = APIRouter(tags=["intelligence-dashboard"])

    @router.get("/intelligence", response_class=HTMLResponse, include_in_schema=False)
    async def intelligence_dashboard_page() -> HTMLResponse:
        html_path = Path(__file__).resolve().parents[3] / "static" / "intelligence.html"
        if not html_path.is_file():
            raise HTTPException(status_code=503, detail="Intelligence dashboard unavailable")
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @router.get("/v1/intelligence/status")
    async def intelligence_status(
        _current_user=Depends(get_current_user),
    ) -> dict[str, Any]:
        return build_intelligence_status()

    return router
