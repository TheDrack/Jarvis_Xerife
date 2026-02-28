# -*- coding: utf-8 -*-
"""Tests for device management API endpoints"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, MagicMock
from sqlmodel import create_engine, SQLModel

from app.adapters.infrastructure.api_server import create_api_server
from app.application.services import AssistantService
from app.application.services.device_service import DeviceService


@pytest.fixture
def test_engine():
    """Create a test database engine"""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def mock_assistant_service():
    """Create a mock assistant service"""
    mock = Mock(spec=AssistantService)
    mock.is_running = True
    mock.wake_word = "xerife"
    mock.get_command_history = Mock(return_value=[])
    return mock


@pytest.fixture
def test_client(mock_assistant_service, test_engine):
    """Create a test client with the API server"""
    # Inject the test engine into the API server
    app = create_api_server(mock_assistant_service)
    
    # Replace the device service with one using test engine
    device_service = DeviceService(engine=test_engine)
    
    # Inject device_service into app state for testing
    # Note: This is a bit of a hack for testing, but works
    for route in app.routes:
        if hasattr(route, 'endpoint') and hasattr(route.endpoint, '__globals__'):
            if 'device_service' in route.endpoint.__globals__:
                route.endpoint.__globals__['device_service'] = device_service
    
    return TestClient(app)


def get_auth_token(client):
    """Helper function to get authentication token"""
    response = client.post(
        "/token",
        data={"username": "admin", "password": "admin123"}
    )
    return response.json()["access_token"]


def test_register_device(test_client):
    """Test device registration endpoint"""
    token = get_auth_token(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = test_client.post(
        "/v1/devices/register",
        json={
            "name": "Test Phone",
            "type": "mobile",
            "capabilities": [
                {
                    "name": "camera",
                    "description": "Camera access",
                    "metadata": {"resolution": "1080p"}
                },
                {
                    "name": "bluetooth_scan",
                    "description": "Bluetooth scanning",
                    "metadata": {}
                }
            ]
        },
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "device_id" in data
    assert data["device_id"] > 0


def test_list_devices(test_client):
    """Test listing devices endpoint"""
    token = get_auth_token(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Register a device first
    test_client.post(
        "/v1/devices/register",
        json={
            "name": "Test Device",
            "type": "mobile",
            "capabilities": []
        },
        headers=headers
    )
    
    # List devices
    response = test_client.get("/v1/devices", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "devices" in data
    assert data["total"] >= 1


def test_get_device(test_client):
    """Test getting a specific device"""
    token = get_auth_token(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Register a device
    reg_response = test_client.post(
        "/v1/devices/register",
        json={
            "name": "Test Device",
            "type": "desktop",
            "capabilities": [
                {
                    "name": "local_http_request",
                    "description": "Local HTTP",
                    "metadata": {}
                }
            ]
        },
        headers=headers
    )
    device_id = reg_response.json()["device_id"]
    
    # Get device details
    response = test_client.get(f"/v1/devices/{device_id}", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == device_id
    assert data["name"] == "Test Device"
    assert data["type"] == "desktop"
    assert len(data["capabilities"]) == 1


def test_device_heartbeat(test_client):
    """Test device heartbeat endpoint"""
    token = get_auth_token(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Register a device
    reg_response = test_client.post(
        "/v1/devices/register",
        json={
            "name": "Test Device",
            "type": "mobile",
            "capabilities": []
        },
        headers=headers
    )
    device_id = reg_response.json()["device_id"]
    
    # Update status
    response = test_client.put(
        f"/v1/devices/{device_id}/heartbeat",
        json={"status": "offline"},
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "offline"


def test_register_device_without_auth(test_client):
    """Test that registration requires authentication"""
    response = test_client.post(
        "/v1/devices/register",
        json={
            "name": "Test Device",
            "type": "mobile",
            "capabilities": []
        }
    )
    
    assert response.status_code == 401


def test_get_nonexistent_device(test_client):
    """Test getting a device that doesn't exist"""
    token = get_auth_token(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = test_client.get("/v1/devices/999", headers=headers)
    
    assert response.status_code == 404


def test_register_device_with_geolocation(test_client):
    """Test device registration with GPS coordinates"""
    token = get_auth_token(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = test_client.post(
        "/v1/devices/register",
        json={
            "name": "GPS Phone",
            "type": "mobile",
            "capabilities": [
                {
                    "name": "camera",
                    "description": "Camera access",
                    "metadata": {"resolution": "4K"}
                }
            ],
            "lat": -23.5505,
            "lon": -46.6333,
            "last_ip": "192.168.1.100"
        },
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "device_id" in data
    
    # Verify the device has location data
    device_id = data["device_id"]
    device_response = test_client.get(f"/v1/devices/{device_id}", headers=headers)
    device_data = device_response.json()
    
    assert device_data["lat"] == -23.5505
    assert device_data["lon"] == -46.6333
    assert device_data["last_ip"] == "192.168.1.100"


def test_device_heartbeat_with_location(test_client):
    """Test device heartbeat endpoint with location update"""
    token = get_auth_token(test_client)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Register a device
    reg_response = test_client.post(
        "/v1/devices/register",
        json={
            "name": "Mobile Device",
            "type": "mobile",
            "capabilities": [],
            "lat": -23.5505,
            "lon": -46.6333,
        },
        headers=headers
    )
    device_id = reg_response.json()["device_id"]
    
    # Update status with new location
    response = test_client.put(
        f"/v1/devices/{device_id}/heartbeat",
        json={
            "status": "online",
            "lat": -22.9068,
            "lon": -43.1729,
            "last_ip": "192.168.2.50"
        },
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["lat"] == -22.9068
    assert data["lon"] == -43.1729
    assert data["last_ip"] == "192.168.2.50"
