# -*- coding: utf-8 -*-
"""Devices router: /v1/devices/*, /v1/commands/* endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.adapters.infrastructure.api_models import (
    CapabilityModel,
    CommandResultRequest,
    CommandResultResponse,
    DeviceListResponse,
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    DeviceResponse,
    DeviceStatusUpdate,
    User,
)

logger = logging.getLogger(__name__)


def _build_device_response(device: dict) -> DeviceResponse:
    """Convert a device dict to a DeviceResponse model."""
    return DeviceResponse(
        id=device["id"],
        name=device["name"],
        type=device["type"],
        status=device["status"],
        network_id=device.get("network_id"),
        network_type=device.get("network_type"),
        lat=device.get("lat"),
        lon=device.get("lon"),
        last_ip=device.get("last_ip"),
        last_seen=device["last_seen"],
        capabilities=[
            CapabilityModel(
                name=cap["name"],
                description=cap["description"],
                metadata=cap["metadata"],
            )
            for cap in device["capabilities"]
        ],
    )


def create_devices_router(device_service, db_adapter, get_current_user) -> APIRouter:
    """
    Create the devices router.

    Args:
        device_service: DeviceService for device management
        db_adapter: SQLiteHistoryAdapter for command persistence
        get_current_user: Dependency callable for authentication

    Returns:
        Configured APIRouter
    """
    router = APIRouter()

    @router.post("/v1/devices/register", response_model=DeviceRegistrationResponse)
    async def register_device(
        request: DeviceRegistrationRequest,
        current_user: User = Depends(get_current_user),
    ) -> DeviceRegistrationResponse:
        """Register a new device or update an existing one (Protected endpoint)."""
        try:
            logger.info(f"User '{current_user.username}' registering device: {request.name}")
            capabilities = [
                {"name": cap.name, "description": cap.description, "metadata": cap.metadata}
                for cap in request.capabilities
            ]
            device_id = device_service.register_device(
                name=request.name,
                device_type=request.type,
                capabilities=capabilities,
                network_id=request.network_id,
                network_type=request.network_type,
                lat=request.lat,
                lon=request.lon,
                last_ip=request.last_ip,
            )
            if device_id is None:
                raise HTTPException(status_code=500, detail="Failed to register device")
            return DeviceRegistrationResponse(
                success=True,
                device_id=device_id,
                message=f"Device '{request.name}' registered successfully with ID {device_id}",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error registering device: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @router.get("/v1/devices", response_model=DeviceListResponse)
    async def list_devices(
        status: str = None,
        current_user: User = Depends(get_current_user),
    ) -> DeviceListResponse:
        """List all registered devices (Protected endpoint)."""
        try:
            devices = device_service.list_devices(status_filter=status)
            return DeviceListResponse(
                devices=[_build_device_response(d) for d in devices],
                total=len(devices),
            )
        except Exception as e:
            logger.error(f"Error listing devices: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @router.get("/v1/devices/{device_id}", response_model=DeviceResponse)
    async def get_device(
        device_id: int,
        current_user: User = Depends(get_current_user),
    ) -> DeviceResponse:
        """Get details of a specific device (Protected endpoint)."""
        try:
            device = device_service.get_device(device_id)
            if device is None:
                raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
            return _build_device_response(device)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting device: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @router.put("/v1/devices/{device_id}/heartbeat", response_model=DeviceResponse)
    async def device_heartbeat(
        device_id: int,
        status_update: DeviceStatusUpdate,
        current_user: User = Depends(get_current_user),
    ) -> DeviceResponse:
        """Update device status / last-seen timestamp (Protected endpoint)."""
        try:
            success = device_service.update_device_status(
                device_id,
                status_update.status,
                lat=status_update.lat,
                lon=status_update.lon,
                last_ip=status_update.last_ip,
            )
            if not success:
                raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
            device = device_service.get_device(device_id)
            return _build_device_response(device)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating device heartbeat: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    @router.post("/v1/commands/{command_id}/result", response_model=CommandResultResponse)
    async def submit_command_result(
        command_id: int,
        result: CommandResultRequest,
        current_user: User = Depends(get_current_user),
    ) -> CommandResultResponse:
        """
        Submit command execution result from a device (Protected endpoint).

        Implements the feedback loop where devices report execution results back to Jarvis.
        """
        try:
            from app.domain.models.device import CommandResult

            logger.info(
                f"User '{current_user.username}' submitting result for command {command_id} "
                f"from device {result.executor_device_id}"
            )

            with Session(db_adapter.engine) as session:
                command_result = CommandResult(
                    command_id=command_id,
                    executor_device_id=result.executor_device_id,
                    result_data=json.dumps(result.result_data),
                    success=result.success,
                    message=result.message or "",
                )
                session.add(command_result)
                session.commit()
                session.refresh(command_result)

            status_val = "completed" if result.success else "failed"
            db_adapter.update_command_status(
                command_id=command_id,
                status=status_val,
                success=result.success,
                response_text=result.message or (
                    "Command executed successfully on device"
                    if result.success
                    else "Command execution failed on device"
                ),
            )

            return CommandResultResponse(
                success=True,
                command_id=command_id,
                message=f"Result for command {command_id} saved successfully",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting command result: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    return router
