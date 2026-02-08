# Device Orchestration - Distributed Architecture

This document describes the distributed orchestration architecture that allows Jarvis to use local devices (mobile, PC, IoT) as extensions of its capabilities.

## Overview

Jarvis now functions as an **Environment Orchestrator**, coordinating multiple devices to execute commands that require specific capabilities. The cloud-based Jarvis instance can delegate tasks to registered devices based on their available capabilities.

## Architecture Components

### 1. Database Models

#### Device Model
- **id**: Unique identifier
- **name**: Device name (e.g., "Samsung Galaxy S21", "Home PC")
- **type**: Device type (`mobile`, `desktop`, `cloud`, `iot`)
- **status**: Current status (`online`, `offline`)
- **last_seen**: Timestamp of last heartbeat

#### Capability Model
- **id**: Unique identifier
- **device_id**: Reference to parent device
- **name**: Capability name (e.g., `camera`, `bluetooth_scan`, `ir_control`)
- **description**: Human-readable description
- **meta_data**: JSON string with technical details

### 2. Device Service

The `DeviceService` class provides methods for:
- **register_device()**: Register or update a device with its capabilities
- **update_device_status()**: Update device online/offline status
- **list_devices()**: List all registered devices with optional status filter
- **get_device()**: Get details of a specific device
- **find_device_by_capability()**: Find an online device with a specific capability

### 3. API Endpoints

All endpoints require authentication via JWT token.

#### POST /v1/devices/register
Register a new device or update an existing one.

**Request:**
```json
{
  "name": "My Phone",
  "type": "mobile",
  "capabilities": [
    {
      "name": "camera",
      "description": "Rear camera 64MP",
      "metadata": {
        "resolution": "4K",
        "fps": 60
      }
    },
    {
      "name": "bluetooth_scan",
      "description": "Bluetooth LE scanner",
      "metadata": {
        "range": "10m"
      }
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "device_id": 1,
  "message": "Device 'My Phone' registered successfully with ID 1"
}
```

#### GET /v1/devices
List all registered devices.

**Query Parameters:**
- `status` (optional): Filter by status (`online` or `offline`)

**Response:**
```json
{
  "devices": [
    {
      "id": 1,
      "name": "My Phone",
      "type": "mobile",
      "status": "online",
      "last_seen": "2024-02-08T10:30:00",
      "capabilities": [...]
    }
  ],
  "total": 1
}
```

#### GET /v1/devices/{device_id}
Get details of a specific device.

#### PUT /v1/devices/{device_id}/heartbeat
Update device status and last_seen timestamp.

**Request:**
```json
{
  "status": "online"
}
```

### 4. Command Routing

When `AssistantService` executes a command, it:
1. Checks if the command requires a specific capability
2. If yes, queries `DeviceService` for an online device with that capability
3. Routes the command to the device by including `target_device_id` in the response

**Example Response with Device Routing:**
```json
{
  "success": true,
  "message": "Command routed to device: My Phone",
  "data": {
    "target_device_id": 1,
    "target_device_name": "My Phone",
    "required_capability": "camera",
    "requires_device_execution": true
  }
}
```

### 5. Updated System Prompt

The Gemini LLM now understands its role as an **Environment Orchestrator**:
- Can request actions from "Local Bridges"
- Manages physical world interactions (TV, AC, Cameras)
- Coordinates multiple devices based on their capabilities

## Usage Example

### Register a Mobile Device
```bash
curl -X POST http://localhost:8000/v1/devices/register \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Phone",
    "type": "mobile",
    "capabilities": [
      {
        "name": "camera",
        "description": "Device camera",
        "metadata": {"resolution": "1080p"}
      }
    ]
  }'
```

### Send Heartbeat
```bash
curl -X PUT http://localhost:8000/v1/devices/1/heartbeat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "online"}'
```

### List Devices
```bash
curl http://localhost:8000/v1/devices \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Common Capabilities

Here are some common capability names you can use:

- **camera**: Access to device camera
- **bluetooth_scan**: Bluetooth device scanning
- **local_http_request**: Access to local network
- **ir_control**: Infrared blaster for TV/AC control
- **gps**: GPS location access
- **microphone**: Audio recording
- **nfc**: NFC reader/writer
- **wifi_scan**: WiFi network scanning

## Implementation Notes

1. **Database**: Uses SQLModel/SQLAlchemy for ORM, supports SQLite and PostgreSQL
2. **Authentication**: All device endpoints require JWT authentication
3. **Status Management**: Devices should send periodic heartbeats to maintain online status
4. **Capability Matching**: The system finds the first available online device with the required capability
5. **Field Name**: The `metadata` field is named `meta_data` in the database to avoid conflicts with SQLAlchemy's reserved names

## Future Enhancements

To fully enable automatic device routing, the following extensions are needed:

1. Add device-specific command types to `CommandType` enum (e.g., `ACCESS_CAMERA`, `CONTROL_IR`)
2. Update `_get_required_capability()` to map commands to capabilities
3. Add device command function declarations to `AgentService`
4. Enable the LLM to recognize and suggest device-specific commands
5. Implement device-side workers to poll for assigned commands and execute them

## Testing

Run the test suite:
```bash
pytest tests/application/test_device_service.py -v
```

Run manual orchestration test:
```bash
python test_orchestration.py
```

Run integration test:
```bash
python test_assistant_integration.py
```
