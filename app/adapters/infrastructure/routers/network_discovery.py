"""Authenticated network inventory and explicitly requested protocol inspection APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.adapters.infrastructure.api_models import User
from app.application.services.network_discovery_service import discover_passive_neighbors


class DeviceInspectionRequest(BaseModel):
    ip_address: str = Field(..., min_length=7, max_length=45)
    ports: list[int] | None = Field(default=None, min_length=1, max_length=32)
    timeout: float = Field(default=0.75, ge=0.2, le=3.0)
    protocol_checks: bool = True


class CameraDiscoveryRequest(BaseModel):
    timeout: float = Field(default=2.0, ge=0.2, le=5.0)


class MdnsDiscoveryRequest(BaseModel):
    timeout: float = Field(default=2.0, ge=0.2, le=5.0)
    service: str = Field(default="_services._dns-sd._udp.local", min_length=1, max_length=255)


class MqttProbeRequest(BaseModel):
    ip_address: str = Field(..., min_length=7, max_length=45)
    port: int = Field(default=1883, ge=1, le=65535)
    timeout: float = Field(default=1.0, ge=0.2, le=3.0)


def create_network_discovery_router(get_current_user) -> APIRouter:
    router = APIRouter(tags=["network"])

    @router.get("/v1/network/interfaces")
    def list_network_interfaces(current_user: User = Depends(get_current_user)):
        """Read interface addresses on the host running this API; sends no probes."""
        from app.adapters.edge.network_discovery_adapter import network_interfaces

        return network_interfaces()

    @router.get("/v1/network/discovery")
    def discover_network(current_user: User = Depends(get_current_user)):
        """Read only the local ARP neighbor cache; never probes the network."""
        return discover_passive_neighbors()

    @router.post("/v1/network/device/inspect")
    def inspect_network_device(
        request: DeviceInspectionRequest,
        current_user: User = Depends(get_current_user),
    ):
        """Actively inspect exactly one explicitly supplied RFC1918 host."""
        from app.adapters.edge.network_protocol_inspector import inspect_private_device

        try:
            return inspect_private_device(
                request.ip_address,
                ports=request.ports,
                timeout=request.timeout,
                protocol_checks=request.protocol_checks,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/v1/network/cameras/discover")
    def discover_cameras(
        request: CameraDiscoveryRequest,
        current_user: User = Depends(get_current_user),
    ):
        """Send bounded SSDP and ONVIF discovery requests on the local link."""
        from app.adapters.edge.udp_discovery_adapter import discover_camera_protocols

        try:
            return discover_camera_protocols(timeout=request.timeout)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/v1/network/mdns/discover")
    def discover_mdns_services(
        request: MdnsDiscoveryRequest,
        current_user: User = Depends(get_current_user),
    ):
        """Send a bounded mDNS DNS-SD PTR query; does not access advertised services."""
        from app.adapters.edge.mdns_discovery_adapter import discover_mdns

        try:
            return discover_mdns(timeout=request.timeout, service=request.service)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=503, detail=f"mDNS indisponivel neste host: {type(exc).__name__}") from exc

    @router.post("/v1/network/mqtt/probe")
    def probe_mqtt_broker(
        request: MqttProbeRequest,
        current_user: User = Depends(get_current_user),
    ):
        """Perform an unauthenticated MQTT CONNECT/CONNACK probe on one host."""
        from app.adapters.edge.mqtt_protocol_probe import probe_mqtt

        if request.port not in (1883, 8883):
            raise HTTPException(status_code=422, detail="Porta MQTT deve ser 1883 ou 8883.")
        try:
            return probe_mqtt(
                request.ip_address,
                port=request.port,
                timeout=request.timeout,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
