# Context and Proximity Routing - Intelligent Device Selection

## Overview

The Context and Proximity Routing feature enables Jarvis to make intelligent decisions about which device should execute a command based on the user's location and network context. This ensures that personal commands (like taking a selfie) execute on the device where the user is, while environment commands (like turning on lights) execute on devices in the same physical location.

## Key Concepts

### Request Metadata

Every command can include context information:
- `source_device_id`: The ID of the device that sent the command
- `network_id`: Network identifier (WiFi SSID or public IP)
- `network_type`: Type of network (wifi, 4g, 5g, ethernet)

### Routing Priority

When routing a command that requires a specific capability (e.g., camera), the system follows this priority:

1. **Priority 1 (Score: 100)**: Source Device
   - If the device that sent the command has the required capability, use it
   - Example: User asks for a selfie from their phone → Use that phone's camera

2. **Priority 2 (Score: 50)**: Same Network Devices
   - Devices on the same network are likely in the same physical location
   - Example: User asks to turn on TV from phone on HomeWiFi → Use IoT device on HomeWiFi

3. **Priority 3 (Score: 10)**: Other Online Devices
   - Fallback to any available online device with the capability
   - Used when no contextual match is found

## Conflict Detection

The system automatically detects potential routing conflicts and asks for user confirmation:

### Scenario 1: Mobile Network to Fixed Network
- **When**: Source device is on 4G/5G, target device is on WiFi/Ethernet
- **Example**: User in car (4G) asks to play music, but music player is on home PC (WiFi)
- **Action**: Ask "Deseja tocar em casa ou no seu celular atual?"

### Scenario 2: Different Networks
- **When**: Source and target devices are on completely different networks
- **Example**: User at office asks to control home IoT device
- **Action**: Ask for confirmation before routing

## API Usage

### Registering a Device with Network Context

```http
POST /v1/devices/register
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "My Phone",
  "type": "mobile",
  "network_id": "HomeWiFi-5GHz",
  "network_type": "wifi",
  "capabilities": [
    {
      "name": "camera",
      "description": "Device camera access",
      "metadata": {"resolution": "1080p"}
    }
  ]
}
```

### Executing a Command with Context

```http
POST /v1/execute
Authorization: Bearer <token>
Content-Type: application/json

{
  "command": "tire uma selfie",
  "metadata": {
    "source_device_id": 1,
    "network_id": "HomeWiFi-5GHz",
    "network_type": "wifi"
  }
}
```

### Submitting Command Results

After a device executes a command, it can report back the result:

```http
POST /v1/commands/{command_id}/result
Authorization: Bearer <token>
Content-Type: application/json

{
  "executor_device_id": 1,
  "success": true,
  "message": "Photo captured successfully",
  "result_data": {
    "photo_url": "https://storage.example.com/selfie-123.jpg",
    "resolution": "1080p",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

## AI Location Intelligence

The Gemini AI is configured with location awareness rules:

### Golden Rule
"If the user asks for something personal (selfie, play music), use the device where they are. If they ask for something environmental (turn on light), use the device in that location."

### Examples

**Personal Commands** (use source device):
- "tire uma selfie" → Use camera on device that sent command
- "toque música" → Play on device where user is
- "abra meu e-mail" → Open on current device

**Environmental Commands** (use same network):
- "ligue a TV" → Use IoT device on same network
- "ajuste o ar condicionado" → Control AC in same location
- "acenda as luzes" → Control lights in same physical space

## Database Schema

### Device Model Updates

```python
class Device(SQLModel, table=True):
    id: int
    name: str
    type: str  # mobile, desktop, cloud, iot
    status: str  # online, offline
    network_id: Optional[str]  # WiFi SSID or public IP
    network_type: Optional[str]  # wifi, 4g, 5g, ethernet
    last_seen: datetime
    created_at: datetime
```

### CommandResult Table

```python
class CommandResult(SQLModel, table=True):
    id: int
    command_id: int  # References Interaction.id
    executor_device_id: Optional[int]  # FK to devices.id
    result_data: str  # JSON string
    success: bool
    message: str
    created_at: datetime
```

## Implementation Details

### DeviceService.find_device_by_capability()

```python
device = device_service.find_device_by_capability(
    capability_name="camera",
    source_device_id=1,  # Optional: prioritize this device
    network_id="HomeWiFi-5GHz"  # Optional: prioritize same network
)
```

Returns the best matching device based on:
1. Whether it's the source device
2. Whether it's on the same network
3. Whether it's online and has the capability

### DeviceService.validate_device_routing()

```python
validation = device_service.validate_device_routing(
    source_device_id=1,
    target_device_id=2
)

if validation["requires_confirmation"]:
    # Ask user for confirmation
    print(validation["reason"])
```

Returns information about potential conflicts and whether user confirmation is needed.

## Testing

Comprehensive test suite covers:
- ✅ Device registration with network information
- ✅ Priority routing (source device gets highest priority)
- ✅ Same network routing (medium priority)
- ✅ Fallback routing (lowest priority)
- ✅ Conflict detection (4G to WiFi)
- ✅ Conflict detection (different networks)
- ✅ No source device scenario

Run tests:
```bash
pytest tests/application/test_device_service.py -k "priority or routing or network" -v
```

## Security Considerations

1. **Network Isolation**: The system detects when commands cross network boundaries and asks for confirmation
2. **No FK Constraint on command_id**: Avoids circular dependency between domain and infrastructure layers
3. **Optional Metadata**: All context fields are optional to maintain backward compatibility
4. **CodeQL Validated**: No security vulnerabilities detected (0 alerts)

## Future Enhancements

Potential improvements:
- GPS-based proximity detection for mobile devices
- User preferences for default device per command type
- Time-based routing (e.g., use bedroom devices at night)
- Multi-device orchestration (execute on multiple devices simultaneously)
- Device capability learning (track which devices users prefer for certain tasks)

## Migration Notes

This feature is fully backward compatible:
- Existing devices without network information continue to work
- Commands without metadata fall back to standard capability matching
- Database migrations are handled automatically via SQLModel

## Contributing

When adding new capabilities:
1. Register devices with accurate network information
2. Consider whether the capability is personal or environmental
3. Test with different network configurations
4. Update the AI system instructions if needed
