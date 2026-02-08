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
