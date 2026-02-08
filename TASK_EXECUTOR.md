# Jarvis Task Executor

## Overview

The **Jarvis Task Executor** is a distributed serverless function execution system that allows the Jarvis AI assistant to execute Python scripts on remote Worker devices with full dependency management and browser automation capabilities.

## Architecture

The Task Executor system consists of three main components:

### 1. TaskRunner (Ephemeral Execution Module)

**Location**: `app/application/services/task_runner.py`

The TaskRunner is responsible for executing Python scripts in isolated environments with automatic dependency management.

#### Features:

- **Virtual Environment Management**: Creates temporary or persistent virtual environments for script execution
- **Dependency Installation**: Automatically installs required Python packages
- **Output Capture**: Captures stdout and stderr from script execution
- **Timeout Support**: Enforces execution time limits to prevent runaway scripts
- **Environment Persistence**: Optionally keeps environments alive for repeated executions
- **Library Caching**: Avoids repeated downloads by caching dependencies

#### Usage:

```python
from app.application.services.task_runner import TaskRunner
from app.domain.models.mission import Mission

# Initialize TaskRunner
task_runner = TaskRunner(cache_dir="/path/to/cache", use_venv=True)

# Create a mission
mission = Mission(
    mission_id="task_001",
    code="print('Hello from Worker!')",
    requirements=["requests", "beautifulsoup4"],
    browser_interaction=False,
    keep_alive=False,
    timeout=300
)

# Execute the mission
result = task_runner.execute_mission(mission)

# Check results
print(f"Success: {result.success}")
print(f"Output: {result.stdout}")
print(f"Execution time: {result.execution_time}s")
```

### 2. PersistentBrowserManager (Playwright Integration)

**Location**: `app/application/services/browser_manager.py`

The PersistentBrowserManager maintains a persistent Playwright browser instance that preserves user sessions (logins, cookies) across automation tasks.

#### Features:

- **Persistent User Data**: Maintains browser profile with saved logins and cookies
- **CDP Connection**: Provides Chrome DevTools Protocol endpoint for script connections
- **Codegen Recording**: Records user interactions and generates Python automation code
- **Browser Lifecycle Management**: Start, stop, and monitor browser status
- **Headless Mode Support**: Can run in headless mode for server deployments

#### Usage:

```python
from app.application.services.browser_manager import PersistentBrowserManager

# Initialize browser manager
browser_manager = PersistentBrowserManager(
    user_data_dir="/home/user/.jarvis/browser_data",
    headless=False,
    browser_type="chromium"
)

# Start the browser
cdp_url = browser_manager.start_browser(port=9222)
print(f"Browser running at: {cdp_url}")

# Use in scripts via CDP
# playwright.chromium.connect_over_cdp(cdp_url)

# Check status
if browser_manager.is_running():
    print(f"CDP URL: {browser_manager.get_cdp_url()}")

# Record automation
output_file = browser_manager.record_automation()
print(f"Recording saved to: {output_file}")

# Stop browser when done
browser_manager.stop_browser()
```

### 3. Mission Models

**Location**: `app/domain/models/mission.py`

Mission models define the contract for task execution payloads.

#### Mission Schema:

```python
{
    "mission_id": "unique_mission_identifier",
    "code": "print('Python code to execute')",
    "requirements": ["package1", "package2"],
    "browser_interaction": false,
    "keep_alive": false,
    "target_device_id": 123,
    "timeout": 300,
    "metadata": {
        "key": "value"
    }
}
```

#### MissionResult Schema:

```python
{
    "mission_id": "unique_mission_identifier",
    "success": true,
    "stdout": "Captured output",
    "stderr": "Captured errors",
    "exit_code": 0,
    "execution_time": 1.234,
    "error": null,
    "metadata": {
        "venv_path": "/path/to/venv",
        "script_path": "/path/to/script.py",
        "persistent": false
    }
}
```

## API Endpoints

### Execute Mission

**POST** `/v1/missions/execute`

Execute a Python script on the Worker device.

**Request Body:**
```json
{
    "mission_id": "mission_123",
    "code": "import requests\nresponse = requests.get('https://api.github.com')\nprint(response.status_code)",
    "requirements": ["requests"],
    "browser_interaction": false,
    "keep_alive": false,
    "timeout": 300,
    "metadata": {}
}
```

**Response:**
```json
{
    "mission_id": "mission_123",
    "success": true,
    "stdout": "200\n",
    "stderr": "",
    "exit_code": 0,
    "execution_time": 1.5,
    "error": null,
    "metadata": {
        "venv_path": null,
        "script_path": "/tmp/mission_123/script.py",
        "persistent": false
    }
}
```

### Control Browser

**POST** `/v1/browser/control`

Control the persistent browser instance.

**Request Body:**
```json
{
    "operation": "start",
    "port": 9222
}
```

**Operations:**
- `start`: Start the browser
- `stop`: Stop the browser
- `status`: Get browser status

**Response:**
```json
{
    "success": true,
    "is_running": true,
    "cdp_url": "http://localhost:9222",
    "message": "Browser started successfully"
}
```

### Record Automation

**POST** `/v1/browser/record`

Start recording browser automation with Playwright codegen.

**Request Body:**
```json
{
    "output_file": "/path/to/save/skill.py"
}
```

**Response:**
```json
{
    "success": true,
    "output_file": "/tmp/jarvis_recordings/skill_1234567890.py",
    "message": "Recording started. Close the browser when done recording."
}
```

## Integration with AssistantService

The Task Executor integrates with the AssistantService through the DeviceService for intelligent routing:

```python
# AssistantService can dispatch missions to specific devices
from app.application.services import AssistantService

# Mission is automatically routed to the appropriate device
# based on capabilities, network proximity, and geographic location
response = assistant_service.process_command(
    "execute Python script on home PC",
    request_metadata={
        "source_device_id": 1,
        "network_id": "home_wifi"
    }
)
```

## Workflow Examples

### Example 1: Simple Script Execution

```python
# Cloud sends mission to Worker
mission = {
    "mission_id": "calc_001",
    "code": """
result = 2 + 2
print(f"Result: {result}")
""",
    "requirements": [],
    "browser_interaction": False,
    "keep_alive": False
}

# Worker executes and returns result
# Output: "Result: 4"
```

### Example 2: Web Scraping with Dependencies

```python
mission = {
    "mission_id": "scrape_001",
    "code": """
import requests
from bs4 import BeautifulSoup

response = requests.get('https://example.com')
soup = BeautifulSoup(response.text, 'html.parser')
title = soup.find('title').text
print(f"Page title: {title}")
""",
    "requirements": ["requests", "beautifulsoup4"],
    "browser_interaction": False,
    "keep_alive": False
}
```

### Example 3: Browser Automation

```python
# First, start the persistent browser
browser_control = {
    "operation": "start",
    "port": 9222
}

# Then send automation mission
mission = {
    "mission_id": "browse_001",
    "code": """
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # Connect to existing browser
    browser = p.chromium.connect_over_cdp('http://localhost:9222')
    page = browser.contexts[0].pages[0]
    
    # Navigate and interact
    page.goto('https://github.com')
    page.screenshot(path='screenshot.png')
    
    print("Screenshot saved!")
""",
    "requirements": ["playwright"],
    "browser_interaction": True,
    "keep_alive": True  # Keep browser running
}
```

### Example 4: Recording New Skills

```python
# Start codegen recording
record_request = {
    "output_file": "/skills/login_to_gmail.py"
}

# User interacts with browser
# Codegen generates code automatically

# Generated code is saved and can be stored as a new skill
# in the database for future use
```

## Security Considerations

1. **Code Execution**: The Task Executor executes arbitrary Python code. Ensure proper authentication and authorization.
2. **Resource Limits**: Set appropriate timeouts and resource limits to prevent abuse.
3. **Dependency Validation**: Validate package names to prevent installation of malicious packages.
4. **Network Isolation**: Consider running tasks in isolated network environments.
5. **User Data Protection**: Browser user data contains sensitive information (cookies, passwords).

## Performance Optimization

1. **Library Caching**: Use `cache_dir` to avoid repeated package downloads.
2. **Environment Persistence**: Use `keep_alive=True` for frequently used dependency sets.
3. **Headless Browsers**: Use headless mode for automation that doesn't require visual feedback.
4. **Background Execution**: Long-running tasks should be executed asynchronously.

## Troubleshooting

### Issue: Virtual environment creation fails

**Solution**: Ensure Python has the `venv` module installed:
```bash
python -m ensurepip
python -m pip install --upgrade pip
```

### Issue: Playwright browser not found

**Solution**: Install Playwright browsers:
```bash
pip install playwright
playwright install chromium
```

### Issue: CDP connection fails

**Solution**: Ensure the browser is running and the port is not blocked:
```bash
# Check if browser is running
curl http://localhost:9222/json/version
```

### Issue: Package installation timeout

**Solution**: Increase timeout or pre-warm the environment:
```python
task_runner = TaskRunner(cache_dir="/persistent/cache")
# Install common packages ahead of time
```

## Future Enhancements

1. **Docker Integration**: Execute tasks in Docker containers for better isolation.
2. **GPU Support**: Enable GPU access for ML/AI tasks.
3. **Streaming Output**: Stream stdout/stderr in real-time for long-running tasks.
4. **Skill Repository**: Build a repository of recorded automation skills.
5. **Multi-Browser Support**: Support Firefox and WebKit browsers.
6. **Resource Monitoring**: Track CPU, memory, and network usage per mission.

## Related Documentation

- [Architecture Overview](ARCHITECTURE.md)
- [API Documentation](API_README.md)
- [Device Orchestration](DEVICE_ORCHESTRATION.md)
- [Distributed Mode](DISTRIBUTED_MODE.md)
