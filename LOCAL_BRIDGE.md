# JARVIS Local Bridge

## Overview

The **Local Bridge** is a WebSocket-based connection that allows JARVIS (running in the cloud/Render) to delegate GUI tasks to your local PC. This enables JARVIS to perform actions that require direct hardware access, like PyAutoGUI operations.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  JARVIS (Cloud/Render)                      │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  API Server                                          │ │
│  │  /v1/local-bridge (WebSocket)                        │ │
│  └──────────────────────────────────────────────────────┘ │
└───────────────────────┬─────────────────────────────────────┘
                        │ WebSocket Connection
                        │ (wss://your-jarvis.onrender.com)
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                   Local PC (Your Computer)                  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Local Bridge Client                                 │ │
│  │  - Connects to JARVIS WebSocket                      │ │
│  │  - Receives task commands                            │ │
│  │  - Executes PyAutoGUI operations                     │ │
│  │  - Returns results to JARVIS                         │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Why Local Bridge?

JARVIS runs in the cloud (Render), which doesn't have access to:
- Your computer's display (GUI)
- Mouse and keyboard control
- Local files and applications

The Local Bridge solves this by delegating these tasks to your local PC while JARVIS coordinates from the cloud.

## WebSocket Endpoint

```
ws://your-jarvis-host/v1/local-bridge?device_id=my_pc
```

Or for HTTPS:
```
wss://your-jarvis-host/v1/local-bridge?device_id=my_pc
```

## REST Endpoints

### List Connected Devices
```bash
GET /v1/local-bridge/devices
```

Response:
```json
{
  "connected_devices": ["my_pc", "laptop"],
  "count": 2
}
```

### Send Task to Device
```bash
POST /v1/local-bridge/send-task?device_id=my_pc
Content-Type: application/json

{
  "action": "click",
  "parameters": {
    "x": 100,
    "y": 200
  }
}
```

## Local Client Implementation

### Python Client (Recommended)

```python
# local_bridge_client.py
"""
JARVIS Local Bridge Client

Connects your local PC to JARVIS in the cloud, enabling GUI delegation.
"""

import asyncio
import websockets
import json
import os
import logging

# PyAutoGUI for GUI automation (install: pip install pyautogui)
try:
    import pyautogui
    HAS_GUI = True
except ImportError:
    HAS_GUI = False
    print("⚠️  PyAutoGUI not installed. Install with: pip install pyautogui")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LocalBridgeClient:
    """Client for connecting local PC to JARVIS"""
    
    def __init__(self, jarvis_url: str, device_id: str = "my_pc"):
        """
        Initialize the client.
        
        Args:
            jarvis_url: JARVIS WebSocket URL (ws://host/v1/local-bridge)
            device_id: Unique identifier for this device
        """
        self.jarvis_url = f"{jarvis_url}?device_id={device_id}"
        self.device_id = device_id
    
    async def execute_task(self, task: dict) -> dict:
        """
        Execute a task from JARVIS.
        
        Args:
            task: Task definition
            
        Returns:
            Task result
        """
        action = task.get("action")
        params = task.get("parameters", {})
        
        try:
            if action == "click":
                # Mouse click
                x = params.get("x", 0)
                y = params.get("y", 0)
                if HAS_GUI:
                    pyautogui.click(x, y)
                    return {"success": True, "result": f"Clicked at ({x}, {y})"}
                else:
                    return {"success": False, "error": "PyAutoGUI not available"}
            
            elif action == "type":
                # Type text
                text = params.get("text", "")
                if HAS_GUI:
                    pyautogui.write(text)
                    return {"success": True, "result": f"Typed: {text}"}
                else:
                    return {"success": False, "error": "PyAutoGUI not available"}
            
            elif action == "screenshot":
                # Take screenshot
                if HAS_GUI:
                    screenshot = pyautogui.screenshot()
                    screenshot.save("jarvis_screenshot.png")
                    return {"success": True, "result": "Screenshot saved"}
                else:
                    return {"success": False, "error": "PyAutoGUI not available"}
            
            elif action == "hotkey":
                # Press hotkey combination
                keys = params.get("keys", [])
                if HAS_GUI:
                    pyautogui.hotkey(*keys)
                    return {"success": True, "result": f"Pressed: {'+'.join(keys)}"}
                else:
                    return {"success": False, "error": "PyAutoGUI not available"}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        
        except Exception as e:
            logger.error(f"Task execution error: {e}")
            return {"success": False, "error": str(e)}
    
    async def connect(self):
        """Connect to JARVIS and handle tasks"""
        logger.info(f"Connecting to JARVIS: {self.jarvis_url}")
        
        try:
            async with websockets.connect(self.jarvis_url) as websocket:
                logger.info("✓ Connected to JARVIS!")
                
                # Receive welcome message
                welcome = await websocket.recv()
                logger.info(f"JARVIS: {welcome}")
                
                # Handle tasks in a loop
                while True:
                    try:
                        # Receive task from JARVIS
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        msg_type = data.get("type")
                        
                        if msg_type == "task":
                            # Execute task
                            task_id = data.get("task_id")
                            logger.info(f"Received task: {data.get('action')}")
                            
                            result = await self.execute_task(data)
                            
                            # Send result back to JARVIS
                            response = {
                                "type": "task_result",
                                "task_id": task_id,
                                "success": result.get("success", False),
                                "result": result.get("result"),
                                "error": result.get("error")
                            }
                            await websocket.send(json.dumps(response))
                            logger.info(f"Task result sent: {result.get('success')}")
                        
                        elif msg_type == "heartbeat_ack":
                            logger.debug("Heartbeat acknowledged")
                        
                        else:
                            logger.warning(f"Unknown message type: {msg_type}")
                    
                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Connection closed by JARVIS")
                        break
                    except json.JSONDecodeError:
                        logger.error("Invalid JSON received")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}")
        
        except Exception as e:
            logger.error(f"Connection error: {e}")

def main():
    """Main entry point"""
    # Configuration
    JARVIS_URL = os.getenv("JARVIS_WS_URL", "ws://localhost:8000/v1/local-bridge")
    DEVICE_ID = os.getenv("DEVICE_ID", "my_pc")
    
    # Create and run client
    client = LocalBridgeClient(JARVIS_URL, DEVICE_ID)
    
    print("=" * 70)
    print("  JARVIS Local Bridge Client")
    print("=" * 70)
    print(f"  Device ID: {DEVICE_ID}")
    print(f"  Connecting to: {JARVIS_URL}")
    print("=" * 70)
    print()
    
    # Run the client
    asyncio.run(client.connect())

if __name__ == "__main__":
    main()
```

### Installation

```bash
# Install dependencies
pip install websockets pyautogui

# Set environment variables (optional)
export JARVIS_WS_URL="wss://your-jarvis.onrender.com/v1/local-bridge"
export DEVICE_ID="my_laptop"

# Run the client
python local_bridge_client.py
```

## Usage Examples

### Example 1: Click at Position

From JARVIS:
```python
from app.application.services.local_bridge import get_bridge_manager

bridge = get_bridge_manager()
result = await bridge.send_task("my_pc", {
    "action": "click",
    "parameters": {"x": 500, "y": 300}
})

print(result)  # {"success": True, "result": "Clicked at (500, 300)"}
```

### Example 2: Type Text

```python
result = await bridge.send_task("my_pc", {
    "action": "type",
    "parameters": {"text": "Hello from JARVIS!"}
})
```

### Example 3: Press Hotkey

```python
# Press Ctrl+C
result = await bridge.send_task("my_pc", {
    "action": "hotkey",
    "parameters": {"keys": ["ctrl", "c"]}
})
```

### Example 4: Take Screenshot

```python
result = await bridge.send_task("my_pc", {
    "action": "screenshot",
    "parameters": {}
})
```

## Supported Actions

| Action | Parameters | Description |
|--------|------------|-------------|
| `click` | `x`, `y` | Click mouse at position |
| `type` | `text` | Type text |
| `hotkey` | `keys` (list) | Press key combination |
| `screenshot` | - | Take screenshot |
| `move` | `x`, `y` | Move mouse |
| `drag` | `x1`, `y1`, `x2`, `y2` | Drag mouse |

You can extend the client with more actions as needed.

## Security Considerations

⚠️ **Important Security Notes:**

1. **Authentication**: The current implementation doesn't include authentication. In production, add:
   - API tokens for device authentication
   - Rate limiting
   - IP whitelisting

2. **HTTPS/WSS**: Always use secure WebSocket (wss://) in production

3. **Permissions**: The local client can control your PC - only connect trusted JARVIS instances

4. **Firewall**: Ensure your firewall allows WebSocket connections

## Advanced Usage

### Multiple Devices

Connect multiple PCs with different device IDs:

```bash
# On PC 1
DEVICE_ID="desktop" python local_bridge_client.py

# On PC 2
DEVICE_ID="laptop" python local_bridge_client.py
```

### Heartbeat

Send periodic heartbeats to keep connection alive:

```python
async def heartbeat_loop(websocket):
    while True:
        await asyncio.sleep(30)
        await websocket.send(json.dumps({"type": "heartbeat"}))
```

### Task Queue

The bridge manager maintains task queues for each connected device, ensuring tasks are executed in order.

## Troubleshooting

### Connection Refused

- Check JARVIS is running
- Verify the WebSocket URL
- Check firewall settings

### PyAutoGUI Errors

- Ensure you're not running in a headless environment
- On Linux, you may need `xdotool`: `sudo apt-get install xdotool`

### Connection Drops

- Check network stability
- Implement reconnection logic in client
- Use heartbeats to detect stale connections

## Future Enhancements

- [ ] Device capabilities discovery
- [ ] File transfer support
- [ ] Screen streaming
- [ ] Multi-monitor support
- [ ] Voice command execution
- [ ] Clipboard synchronization

---

**JARVIS Local Bridge: Extending JARVIS to your physical world** 🌐💻
