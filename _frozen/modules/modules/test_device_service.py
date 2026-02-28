# -*- coding: utf-8 -*-
"""Tests for device management service"""

import pytest
from datetime import datetime
from sqlmodel import create_engine, Session, SQLModel

from app.application.services.device_service import DeviceService
from app.domain.models.device import Device, Capability


@pytest.fixture
def test_engine():
    """Create a test database engine"""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def device_service(test_engine):
    """Create a device service instance"""
    return DeviceService(engine=test_engine)


def test_register_new_device(device_service):
    """Test registering a new device"""
    capabilities = [
        {
            "name": "camera",
            "description": "Device camera access",
            "metadata": {"resolution": "1080p"},
        },
        {
            "name": "bluetooth_scan",
            "description": "Bluetooth scanning capability",
            "metadata": {"range": "10m"},
        },
    ]
    
    device_id = device_service.register_device(
        name="Test Phone",
        device_type="mobile",
        capabilities=capabilities,
    )
    
    assert device_id is not None
    assert isinstance(device_id, int)
    
    # Verify device was created
    device = device_service.get_device(device_id)
    assert device is not None
    assert device["name"] == "Test Phone"
    assert device["type"] == "mobile"
    assert device["status"] == "online"
    assert len(device["capabilities"]) == 2


def test_update_existing_device(device_service):
    """Test updating an existing device"""
    # Register initial device
    initial_capabilities = [
        {
            "name": "camera",
            "description": "Device camera",
            "metadata": {},
        },
    ]
    
    device_id = device_service.register_device(
        name="Test Device",
        device_type="mobile",
        capabilities=initial_capabilities,
    )
    
    # Update the same device with new capabilities
    updated_capabilities = [
        {
            "name": "camera",
            "description": "Updated camera",
            "metadata": {"resolution": "4K"},
        },
        {
            "name": "gps",
            "description": "GPS location",
            "metadata": {},
        },
    ]
    
    updated_id = device_service.register_device(
        name="Test Device",
        device_type="desktop",
        capabilities=updated_capabilities,
    )
    
    # Should get the same device ID
    assert updated_id == device_id
    
    # Verify device was updated
    device = device_service.get_device(device_id)
    assert device["type"] == "desktop"
    assert len(device["capabilities"]) == 2


def test_update_device_status(device_service):
    """Test updating device status"""
    device_id = device_service.register_device(
        name="Test Device",
        device_type="mobile",
        capabilities=[],
    )
    
    # Update status to offline
    success = device_service.update_device_status(device_id, "offline")
    assert success is True
    
    device = device_service.get_device(device_id)
    assert device["status"] == "offline"
    
    # Update status back to online
    success = device_service.update_device_status(device_id, "online")
    assert success is True
    
    device = device_service.get_device(device_id)
    assert device["status"] == "online"


def test_list_devices(device_service):
    """Test listing devices"""
    # Register multiple devices
    device_service.register_device("Device 1", "mobile", [])
    device_service.register_device("Device 2", "desktop", [])
    
    # List all devices
    devices = device_service.list_devices()
    assert len(devices) == 2
    
    # Set one device offline
    device_service.update_device_status(1, "offline")
    
    # List only online devices
    online_devices = device_service.list_devices(status_filter="online")
    assert len(online_devices) == 1
    
    # List only offline devices
    offline_devices = device_service.list_devices(status_filter="offline")
    assert len(offline_devices) == 1


def test_find_device_by_capability(device_service):
    """Test finding devices by capability"""
    # Register device with camera capability
    device_service.register_device(
        name="Phone with Camera",
        device_type="mobile",
        capabilities=[
            {
                "name": "camera",
                "description": "Camera access",
                "metadata": {},
            },
        ],
    )
    
    # Register device without camera
    device_service.register_device(
        name="Desktop PC",
        device_type="desktop",
        capabilities=[
            {
                "name": "local_http_request",
                "description": "Local network access",
                "metadata": {},
            },
        ],
    )
    
    # Find device with camera capability
    device = device_service.find_device_by_capability("camera")
    assert device is not None
    assert device["name"] == "Phone with Camera"
    
    # Find device with non-existent capability
    device = device_service.find_device_by_capability("nonexistent")
    assert device is None


def test_find_device_by_capability_online_only(device_service):
    """Test that only online devices are returned when finding by capability"""
    # Register device with camera
    device_id = device_service.register_device(
        name="Phone",
        device_type="mobile",
        capabilities=[
            {
                "name": "camera",
                "description": "Camera",
                "metadata": {},
            },
        ],
    )
    
    # Should find the device when online
    device = device_service.find_device_by_capability("camera")
    assert device is not None
    
    # Set device offline
    device_service.update_device_status(device_id, "offline")
    
    # Should not find the device when offline
    device = device_service.find_device_by_capability("camera")
    assert device is None


def test_get_nonexistent_device(device_service):
    """Test getting a device that doesn't exist"""
    device = device_service.get_device(999)
    assert device is None


def test_update_nonexistent_device_status(device_service):
    """Test updating status of a device that doesn't exist"""
    success = device_service.update_device_status(999, "online")
    assert success is False


# Context and Proximity Routing Tests


def test_register_device_with_network_info(device_service):
    """Test registering a device with network information"""
    device_id = device_service.register_device(
        name="Test Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        network_id="HomeWiFi-5GHz",
        network_type="wifi",
    )
    
    assert device_id is not None
    
    device = device_service.get_device(device_id)
    assert device is not None
    assert device["network_id"] == "HomeWiFi-5GHz"
    assert device["network_type"] == "wifi"


def test_find_device_priority_source_device(device_service):
    """Test that source device gets highest priority when it has the capability"""
    # Register source device with camera
    source_id = device_service.register_device(
        name="Source Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        network_id="4G-Network",
        network_type="4g",
    )
    
    # Register another device with camera on WiFi
    device_service.register_device(
        name="Home Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        network_id="HomeWiFi",
        network_type="wifi",
    )
    
    # Find device with source_device_id specified
    device = device_service.find_device_by_capability(
        "camera",
        source_device_id=source_id,
    )
    
    # Should return the source device (highest priority)
    assert device is not None
    assert device["id"] == source_id
    assert device["name"] == "Source Phone"


def test_find_device_priority_same_network(device_service):
    """Test that devices on the same network get medium priority"""
    # Register source device without camera
    source_id = device_service.register_device(
        name="Source Device",
        device_type="desktop",
        capabilities=[{"name": "display", "description": "Display", "metadata": {}}],
        network_id="HomeWiFi",
        network_type="wifi",
    )
    
    # Register device with camera on same network
    same_network_id = device_service.register_device(
        name="Same Network Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        network_id="HomeWiFi",
        network_type="wifi",
    )
    
    # Register device with camera on different network
    device_service.register_device(
        name="Different Network Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        network_id="OfficeWiFi",
        network_type="wifi",
    )
    
    # Find device with source info but source doesn't have capability
    device = device_service.find_device_by_capability(
        "camera",
        source_device_id=source_id,
        network_id="HomeWiFi",
    )
    
    # Should return the device on the same network (medium priority)
    assert device is not None
    assert device["id"] == same_network_id
    assert device["name"] == "Same Network Phone"


def test_find_device_priority_fallback(device_service):
    """Test fallback to any online device when no priority matches"""
    # Register device with camera on different network
    fallback_id = device_service.register_device(
        name="Fallback Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        network_id="OfficeWiFi",
        network_type="wifi",
    )
    
    # Find device with different network context
    device = device_service.find_device_by_capability(
        "camera",
        network_id="HomeWiFi",
    )
    
    # Should still return the device as fallback
    assert device is not None
    assert device["id"] == fallback_id
    assert device["name"] == "Fallback Phone"


def test_validate_device_routing_same_network(device_service):
    """Test routing validation when devices are on the same network"""
    source_id = device_service.register_device(
        name="Source",
        device_type="mobile",
        capabilities=[],
        network_id="HomeWiFi",
        network_type="wifi",
    )
    
    target_id = device_service.register_device(
        name="Target",
        device_type="desktop",
        capabilities=[],
        network_id="HomeWiFi",
        network_type="wifi",
    )
    
    validation = device_service.validate_device_routing(source_id, target_id)
    
    assert validation["requires_confirmation"] is False
    assert validation["source_device"] is not None
    assert validation["target_device"] is not None


def test_validate_device_routing_4g_to_wifi_conflict(device_service):
    """Test routing validation when source is on 4G and target is on WiFi"""
    source_id = device_service.register_device(
        name="Mobile",
        device_type="mobile",
        capabilities=[],
        network_id="4G-Network",
        network_type="4g",
    )
    
    target_id = device_service.register_device(
        name="Home PC",
        device_type="desktop",
        capabilities=[],
        network_id="HomeWiFi",
        network_type="wifi",
    )
    
    validation = device_service.validate_device_routing(source_id, target_id)
    
    assert validation["requires_confirmation"] is True
    assert "4G" in validation["reason"]
    assert "rede doméstica" in validation["reason"].lower()


def test_validate_device_routing_different_networks(device_service):
    """Test routing validation when devices are on different networks"""
    source_id = device_service.register_device(
        name="Office Device",
        device_type="desktop",
        capabilities=[],
        network_id="OfficeWiFi",
        network_type="wifi",
    )
    
    target_id = device_service.register_device(
        name="Home Device",
        device_type="desktop",
        capabilities=[],
        network_id="HomeWiFi",
        network_type="wifi",
    )
    
    validation = device_service.validate_device_routing(source_id, target_id)
    
    assert validation["requires_confirmation"] is True
    assert "rede diferente" in validation["reason"].lower()


def test_validate_device_routing_no_source(device_service):
    """Test routing validation when no source device is provided"""
    target_id = device_service.register_device(
        name="Target",
        device_type="desktop",
        capabilities=[],
    )
    
    validation = device_service.validate_device_routing(None, target_id)
    
    assert validation["requires_confirmation"] is False
    assert validation["source_device"] is None
    assert validation["target_device"] is not None


# Geolocation Tests


def test_calculate_distance(device_service):
    """Test distance calculation using Haversine formula"""
    # São Paulo to Rio de Janeiro (approximately 360km)
    sp_lat, sp_lon = -23.5505, -46.6333
    rj_lat, rj_lon = -22.9068, -43.1729
    
    distance = device_service.calculate_distance(sp_lat, sp_lon, rj_lat, rj_lon)
    
    # Should be approximately 360km
    assert 350 < distance < 370


def test_register_device_with_geolocation(device_service):
    """Test registering a device with GPS coordinates"""
    device_id = device_service.register_device(
        name="Mobile Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        lat=-23.5505,
        lon=-46.6333,
        last_ip="192.168.1.100",
    )
    
    device = device_service.get_device(device_id)
    assert device is not None
    assert device["lat"] == -23.5505
    assert device["lon"] == -46.6333
    assert device["last_ip"] == "192.168.1.100"


def test_update_device_status_with_location(device_service):
    """Test updating device status with location data"""
    device_id = device_service.register_device(
        name="Test Device",
        device_type="mobile",
        capabilities=[],
        lat=-23.5505,
        lon=-46.6333,
    )
    
    # Update with new location
    success = device_service.update_device_status(
        device_id,
        "online",
        lat=-22.9068,
        lon=-43.1729,
        last_ip="192.168.2.50",
    )
    
    assert success is True
    
    device = device_service.get_device(device_id)
    assert device["lat"] == -22.9068
    assert device["lon"] == -43.1729
    assert device["last_ip"] == "192.168.2.50"


def test_find_device_priority_geolocation_very_close(device_service):
    """Test that very close devices (<1km) get high priority"""
    # Register source device
    source_id = device_service.register_device(
        name="Source",
        device_type="desktop",
        capabilities=[{"name": "display", "description": "Display", "metadata": {}}],
        lat=-23.5505,
        lon=-46.6333,
    )
    
    # Register very close device with camera (0.5km away)
    close_id = device_service.register_device(
        name="Close Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        lat=-23.5550,
        lon=-46.6333,
    )
    
    # Register far device with camera (in another city)
    device_service.register_device(
        name="Far Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        lat=-22.9068,
        lon=-43.1729,
    )
    
    # Find device with source location
    device = device_service.find_device_by_capability(
        "camera",
        source_device_id=source_id,
        source_lat=-23.5505,
        source_lon=-46.6333,
    )
    
    # Should return the very close device
    assert device is not None
    assert device["id"] == close_id
    assert device["name"] == "Close Phone"


def test_find_device_priority_geolocation_same_city(device_service):
    """Test that devices in same city (<50km) get medium priority"""
    # Register far device with camera (no proximity)
    far_id = device_service.register_device(
        name="Far Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        lat=-22.9068,
        lon=-43.1729,
    )
    
    # Register same-city device with camera (30km away)
    same_city_id = device_service.register_device(
        name="Same City Phone",
        device_type="mobile",
        capabilities=[{"name": "camera", "description": "Camera", "metadata": {}}],
        lat=-23.6505,
        lon=-46.6333,
    )
    
    # Find device with source location
    device = device_service.find_device_by_capability(
        "camera",
        source_lat=-23.5505,
        source_lon=-46.6333,
    )
    
    # Should return the same-city device (closer)
    assert device is not None
    assert device["id"] == same_city_id
    assert device["name"] == "Same City Phone"


def test_validate_device_routing_far_distance(device_service):
    """Test routing validation when devices are in different cities (>50km)"""
    # São Paulo
    source_id = device_service.register_device(
        name="SP Phone",
        device_type="mobile",
        capabilities=[],
        lat=-23.5505,
        lon=-46.6333,
    )
    
    # Rio de Janeiro (approximately 360km from São Paulo)
    target_id = device_service.register_device(
        name="RJ Desktop",
        device_type="desktop",
        capabilities=[],
        lat=-22.9068,
        lon=-43.1729,
    )
    
    validation = device_service.validate_device_routing(source_id, target_id)
    
    assert validation["requires_confirmation"] is True
    assert "km" in validation["reason"]
    assert "distância" in validation["reason"]
    assert validation["distance"] is not None
    assert validation["distance"] > 50


def test_validate_device_routing_same_location(device_service):
    """Test routing validation when devices are very close"""
    # Two devices in the same location
    source_id = device_service.register_device(
        name="Phone 1",
        device_type="mobile",
        capabilities=[],
        lat=-23.5505,
        lon=-46.6333,
    )
    
    target_id = device_service.register_device(
        name="Phone 2",
        device_type="mobile",
        capabilities=[],
        lat=-23.5505,
        lon=-46.6333,
    )
    
    validation = device_service.validate_device_routing(source_id, target_id)
    
    # Should not require confirmation (same location)
    assert validation["requires_confirmation"] is False
    assert validation["distance"] is not None
    assert validation["distance"] < 1
