# -*- coding: utf-8 -*-
"""Utility router: /v1/scavenger-hunt/*, /v1/telemetry, /v1/evolution/status, /v1/roadmap/*."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.infrastructure.api_models import User

logger = logging.getLogger(__name__)

BATTERY_LOW_THRESHOLD = 15  # % – triggers power-saving suggestions
PLUGINS_DYNAMIC_DIR = "app/plugins/dynamic"


def create_utility_router(db_adapter, get_current_user) -> APIRouter:
    """
    Create the utility router (telemetry, scavenger hunt, roadmap, HUD evolution status).

    Args:
        db_adapter: SQLiteHistoryAdapter whose engine is shared with CapabilityManager
        get_current_user: Dependency callable for authentication

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.get("/v1/scavenger-hunt/api-keys")
    async def get_api_key_guides(api_key_names: str = None) -> Dict[str, Any]:
        """
        Get step-by-step guides for obtaining missing API keys.

        Query Params:
            api_key_names: Comma-separated key names (omit to get all guides)
        """
        from app.application.services.scavenger_hunt import ScavengerHunt

        if api_key_names:
            keys = [k.strip() for k in api_key_names.split(",")]
            guides: Dict[str, Any] = {}
            for key in keys:
                guide = ScavengerHunt.find_guide(key)
                if guide:
                    guides[key] = {
                        "service_name": guide.service_name,
                        "key_name": guide.key_name,
                        "steps": guide.steps,
                        "documentation_url": guide.documentation_url,
                        "is_free": guide.is_free,
                        "estimated_time": guide.estimated_time,
                    }
            return guides

        return {
            key: {
                "service_name": g.service_name,
                "key_name": g.key_name,
                "steps": g.steps,
                "documentation_url": g.documentation_url,
                "is_free": g.is_free,
                "estimated_time": g.estimated_time,
            }
            for key, g in ScavengerHunt.API_KEY_GUIDES.items()
        }

    @router.post("/v1/scavenger-hunt/missing-resources")
    async def analyze_missing_resources(capability_id: int) -> Dict[str, Any]:
        """
        Analyze missing resources for a capability and provide acquisition guides.

        Args:
            capability_id: The capability ID to analyze (1–102)
        """
        from app.application.services.capability_manager import CapabilityManager
        from app.application.services.scavenger_hunt import ScavengerHunt

        try:
            capability_manager = CapabilityManager(engine=db_adapter.engine)
            alert = capability_manager.resource_request(capability_id)

            if alert is None:
                return {
                    "capability_id": capability_id,
                    "has_missing_resources": False,
                    "message": "All resources are available for this capability",
                }

            categorized = ScavengerHunt.search_for_missing_resources(alert["missing_resources"])
            api_key_names = [
                res.get("name")
                for res in alert["missing_resources"]
                if res.get("type") == "environment_variable"
            ]
            report = ScavengerHunt.generate_acquisition_report(api_key_names) if api_key_names else None

            return {
                "capability_id": capability_id,
                "capability_name": alert["capability_name"],
                "has_missing_resources": True,
                "missing_resources": alert["missing_resources"],
                "categorized": categorized,
                "acquisition_report": report,
                "alert_level": alert["alert_level"],
            }
        except Exception as e:
            logger.error(f"Error analyzing missing resources: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to analyze resources: {str(e)}")

    @router.post("/v1/telemetry")
    async def receive_telemetry(
        telemetry_data: Dict[str, Any],
        current_user: User = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """
        Receive telemetry data from mobile/desktop clients (battery, GPS, device type).

        Used for context-aware assistance and urgency detection.
        """
        logger.info(f"Telemetry received from {current_user.username}: {telemetry_data}")
        response: Dict[str, Any] = {
            "status": "received",
            "timestamp": datetime.now().isoformat(),
        }

        battery = telemetry_data.get("battery", {})
        battery_level = battery.get("level", 100)
        battery_charging = battery.get("charging", False)

        if battery and battery_level < BATTERY_LOW_THRESHOLD and not battery_charging:
            response["suggestions"] = [
                "Bateria crítica detectada. Sugerindo desativar funções pesadas da HUD.",
                "Reduzir frequência de telemetria para economizar bateria.",
                "Considerar modo de economia de energia.",
            ]
            response["priority"] = "high"
            logger.warning(f"Low battery for {current_user.username}: {battery_level}%")

        return response

    @router.get("/v1/evolution/status")
    async def get_evolution_status_simple(
        current_user: User = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """Get simplified evolution status for HUD display (next plugin + count)."""
        try:
            from app.application.services.capability_manager import CapabilityManager

            capability_manager = CapabilityManager(engine=db_adapter.engine)
            next_step = capability_manager.get_next_evolution_step()

            plugins_dir = Path(PLUGINS_DYNAMIC_DIR)
            plugin_count = (
                len([f for f in plugins_dir.glob("*.py") if f.is_file()])
                if plugins_dir.exists()
                else 0
            )

            if next_step:
                return {
                    "next_plugin": next_step["name"],
                    "status": "Planejando implementação",
                    "plugin_count": plugin_count,
                    "progress": next_step.get("progress", 0),
                }
            return {
                "next_plugin": None,
                "status": "Todas as capacidades implementadas ou aguardando recursos",
                "plugin_count": plugin_count,
                "progress": 100,
            }
        except Exception as e:
            logger.error(f"Error getting evolution status: {e}")
            return {"next_plugin": None, "status": "Erro ao obter status", "plugin_count": 0, "error": str(e)}

    @router.get("/v1/roadmap/progress")
    async def get_roadmap_progress(
        current_user: User = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """Get roadmap completion percentage based on ROADMAP.md missions (HUD display)."""
        try:
            from app.application.services.auto_evolution import AutoEvolutionService

            metrics = AutoEvolutionService().get_success_metrics()

            if "error" in metrics:
                logger.error(f"Error getting roadmap metrics: {metrics['error']}")
                return {
                    "completion_percentage": 0.0,
                    "total_missions": 0,
                    "completed": 0,
                    "in_progress": 0,
                    "planned": 0,
                    "error": metrics["error"],
                }
            return {
                "completion_percentage": metrics["completion_percentage"],
                "total_missions": metrics["total_missions"],
                "completed": metrics["completed"],
                "in_progress": metrics["in_progress"],
                "planned": metrics["planned"],
            }
        except Exception as e:
            logger.error(f"Error getting roadmap progress: {e}")
            return {
                "completion_percentage": 0.0,
                "total_missions": 0,
                "completed": 0,
                "in_progress": 0,
                "planned": 0,
                "error": str(e),
            }

    return router
