# JARVIS Local Agent - Setup Manual

## 🎯 Overview

The JARVIS Local Agent connects your personal Windows/Mac computer to JARVIS running in the cloud (Render), enabling JARVIS to delegate GUI tasks and automation to your local machine.

This is the "Local Bridge" - the connection between JARVIS's cloud brain and your physical computer's arms.

## 📋 Prerequisites

- Python 3.8 or higher
- Windows, macOS, or Linux
- Internet connection
- JARVIS cloud instance URL (from Render deployment)

## 🚀 Quick Start

### Step 1: Install Dependencies

Open your terminal/command prompt and run:

```bash
pip install websockets pyautogui python-dotenv
```

**Package details:**
- `websockets` - WebSocket client for connecting to JARVIS
- `pyautogui` - GUI automation library for mouse/keyboard control
- `python-dotenv` - (Optional) Load configuration from .env file

### Step 2: Create Configuration File

Create a file named `.env` in the same directory as `jarvis_local_agent.py`:

```bash
# JARVIS Local Agent Configuration

# WebSocket URL to your JARVIS instance on Render
# Replace [YOUR-RENDER-URL] with your actual Render URL
JARVIS_WS_URL=wss://[YOUR-RENDER-URL]/v1/local-bridge

# Unique identifier for this device
DEVICE_ID=meu_pc_stark

# Security key - must match the key in JARVIS cloud instance
# Generate a strong random key with: python -c "import secrets; print(secrets.token_hex(32))"
API_KEY_LOCAL=your_secret_key_here_change_this
```

**Important:**
- Use `wss://` (secure WebSocket) for production Render URLs
- Use `ws://` only for local development
- The `API_KEY_LOCAL` must match the key configured in your JARVIS cloud instance

### Step 3: Generate a Secure API Key

Generate a strong random API key:

**On Windows/Mac/Linux:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated key and paste it into your `.env` file as `API_KEY_LOCAL`.

**Important:** Also configure the same key in your JARVIS cloud instance (Render) environment variables.

### Step 4: Run the Agent

```bash
python jarvis_local_agent.py
```

You should see:

```
======================================================================
  ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
  ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
  ██║███████║██████╔╝██║   ██║██║███████╗
  ██║██╔══██║██████╔╝╚██╗ ██╔╝██║╚════██║
  ██║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝

  Local Agent - Connecting your PC to JARVIS Cloud
======================================================================

  Device ID:      meu_pc_stark
  JARVIS URL:     wss://your-jarvis.onrender.com/v1/local-bridge
  API Key:        ******** (configured)
  PyAutoGUI:      ✓ Available
  Screenshots:    ./jarvis_screenshots/
======================================================================

Starting connection to JARVIS...
Press Ctrl+C to stop

✓ Connected to JARVIS!
```

## 🔒 Security Layer

The Local Agent includes a security layer that verifies all commands:

1. **API Key Verification**: Every command from JARVIS must include the correct `API_KEY_LOCAL`
2. **Command Authorization**: Only authorized commands with matching API keys are executed
3. **Rejection Logging**: Unauthorized commands are logged and rejected

**Security Best Practices:**
- Use a strong, random API key (at least 32 characters)
- Never share your API key in public repositories
- Rotate your API key periodically
- Only connect to trusted JARVIS instances
- Monitor the log file (`jarvis_local_agent.log`) for suspicious activity

## 🎮 Supported Actions

The Local Agent supports the following automation actions:

### 1. Click
Click the mouse at a specific position.

**Example:**
```python
# From JARVIS cloud
{
    "action": "click",
    "parameters": {
        "x": 500,
        "y": 300,
        "clicks": 1,
        "button": "left"  # or "right", "middle"
    },
    "api_key": "your_api_key"
}
```

### 2. Type
Type text on the keyboard.

**Example:**
```python
{
    "action": "type",
    "parameters": {
        "text": "Hello from JARVIS!",
        "interval": 0.1  # seconds between keystrokes
    },
    "api_key": "your_api_key"
}
```

### 3. Screenshot
Take a screenshot and save it locally.

**Example:**
```python
{
    "action": "screenshot",
    "parameters": {
        "filename": "my_screenshot.png"  # optional
    },
    "api_key": "your_api_key"
}
```

Screenshots are saved to `./jarvis_screenshots/` directory.

### 4. Open URL
Open a URL in the default web browser.

**Example:**
```python
{
    "action": "open_url",
    "parameters": {
        "url": "https://github.com"
    },
    "api_key": "your_api_key"
}
```

## 🔧 Advanced Configuration

### Custom Screenshot Directory

Screenshots are saved to `./jarvis_screenshots/` by default. The directory is created automatically if it doesn't exist.

### Logging

Logs are written to:
- Console (stdout)
- `jarvis_local_agent.log` file

Log levels can be adjusted in the script if needed.

### Reconnection

The agent automatically reconnects if the connection is lost:
- Default reconnect delay: 5 seconds
- Infinite retry attempts until manually stopped

### Multiple Devices

You can run multiple agents on different devices:

```bash
# On Device 1
DEVICE_ID=pc_escritorio python jarvis_local_agent.py

# On Device 2
DEVICE_ID=pc_quarto python jarvis_local_agent.py
```

Each device needs its own unique `DEVICE_ID`.

## 🐛 Troubleshooting

### Connection Refused

**Problem:** Cannot connect to JARVIS
```
Connection error: [Errno 61] Connection refused
```

**Solutions:**
1. Verify JARVIS cloud instance is running on Render
2. Check the `JARVIS_WS_URL` in your `.env` file
3. Ensure you're using `wss://` for Render URLs (not `ws://`)
4. Check firewall settings

### PyAutoGUI Not Working

**Problem:** PyAutoGUI errors or not available

**Solutions:**

**On macOS:**
```bash
# Grant accessibility permissions
# System Preferences > Security & Privacy > Privacy > Accessibility
# Add Terminal or your Python IDE
```

**On Linux:**
```bash
# Install X11 tools
sudo apt-get install python3-tk python3-dev xdotool
```

**On Windows:**
Usually works out of the box. If not, run as Administrator.

### Invalid API Key

**Problem:** Commands are rejected with "Unauthorized: Invalid API key"

**Solutions:**
1. Verify `API_KEY_LOCAL` in local `.env` matches cloud configuration
2. Check for extra spaces or quotes in the key
3. Regenerate and reconfigure the API key on both sides

### WebSocket Timeout

**Problem:** Connection drops frequently

**Solutions:**
1. Check network stability
2. Ensure Render instance is not sleeping (use free tier hobby dyno or paid plan)
3. Implement heartbeat monitoring (advanced)

## 📊 Usage from JARVIS Cloud

To send tasks to your local agent from JARVIS cloud:

```python
from app.application.services.local_bridge import get_bridge_manager

# Get bridge manager
bridge = get_bridge_manager()

# Send task
result = await bridge.send_task("meu_pc_stark", {
    "action": "click",
    "parameters": {"x": 100, "y": 200},
    "api_key": os.getenv("API_KEY_LOCAL")
})

print(result)
# {"success": True, "result": "Clicked at (100, 200) with left button, 1 times"}
```

## 🎯 Example Workflow

1. **You:** Start Local Agent on your PC
2. **JARVIS:** (Cloud) Receives command "Take a screenshot of my desktop"
3. **JARVIS:** Sends task to your local PC via WebSocket
4. **Local Agent:** Verifies API key, takes screenshot, saves to disk
5. **Local Agent:** Sends result back to JARVIS
6. **JARVIS:** Confirms screenshot was taken

## 🌟 Next Steps

- Explore extending the agent with custom actions
- Integrate with JARVIS workflows for automation
- Set up multiple devices for distributed control
- Implement file transfer capabilities

## 📝 Notes

- The agent must be running for JARVIS to delegate tasks
- Keep the terminal window open while the agent is running
- Use `Ctrl+C` to stop the agent gracefully
- Check logs in `jarvis_local_agent.log` for debugging

## 🆘 Getting Help

If you encounter issues:

1. Check the log file: `jarvis_local_agent.log`
2. Verify all prerequisites are installed
3. Ensure configuration is correct
4. Test connection to JARVIS manually
5. Review the security layer settings

---

**🤖 JARVIS Local Agent: Connecting the cloud brain to your physical arms** 🌐💪
