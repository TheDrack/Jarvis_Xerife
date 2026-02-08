# Jarvis Task Executor - Quick Start Guide

This guide will help you quickly get started with the Jarvis Task Executor system.

## Prerequisites

- Python 3.8 or higher
- pip package manager
- (Optional) Playwright for browser automation

## Installation

### 1. Install Core Dependencies

```bash
# Install the base Jarvis requirements
pip install -r requirements.txt
```

### 2. Install Playwright (Optional - for browser automation)

```bash
# Install Playwright
pip install playwright

# Install browser binaries
playwright install chromium
```

## Quick Start Examples

### Example 1: Simple Script Execution

```python
from app.application.services.task_runner import TaskRunner
from app.domain.models.mission import Mission

# Create TaskRunner
task_runner = TaskRunner(use_venv=False)

# Create a simple mission
mission = Mission(
    mission_id="hello_world",
    code="print('Hello, World!')",
    requirements=[],
)

# Execute
result = task_runner.execute_mission(mission)
print(f"Output: {result.stdout}")
```

### Example 2: Script with Dependencies

```python
from app.application.services.task_runner import TaskRunner
from app.domain.models.mission import Mission

# Create TaskRunner with caching
task_runner = TaskRunner(use_venv=True)

# Create mission with dependencies
mission = Mission(
    mission_id="web_scrape",
    code="""
import requests
response = requests.get('https://api.github.com')
print(f"Status: {response.status_code}")
""",
    requirements=["requests"],
    timeout=60,
)

# Execute
result = task_runner.execute_mission(mission)
print(result.stdout)
```

### Example 3: Browser Automation

```python
from app.application.services.browser_manager import PersistentBrowserManager

# Initialize browser manager
browser_manager = PersistentBrowserManager()

# Start browser
cdp_url = browser_manager.start_browser(port=9222)
print(f"Browser started at: {cdp_url}")

# Now you can connect to it with Playwright scripts
# browser = playwright.chromium.connect_over_cdp(cdp_url)

# Stop when done
browser_manager.stop_browser()
```

## Running the Demo

A comprehensive demo script is included:

```bash
python demo_task_executor.py
```

This will demonstrate:
- Simple script execution
- Dependency management
- Error handling
- Timeout handling
- Browser manager initialization
- Mission serialization

## Using the API

Start the API server:

```bash
python serve.py
```

Then use the REST API:

```bash
# Get authentication token
TOKEN=$(curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123" | jq -r .access_token)

# Execute a mission
curl -X POST http://localhost:8000/v1/missions/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mission_id": "test_001",
    "code": "print(\"Hello from API!\")",
    "requirements": []
  }'

# Start browser
curl -X POST http://localhost:8000/v1/browser/control \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "start",
    "port": 9222
  }'
```

## Common Use Cases

### 1. Data Processing

```python
mission = Mission(
    mission_id="process_data",
    code="""
import json
data = [1, 2, 3, 4, 5]
result = sum(data)
print(json.dumps({"total": result}))
""",
    requirements=[],
)
```

### 2. Web Scraping

```python
mission = Mission(
    mission_id="scrape_news",
    code="""
import requests
from bs4 import BeautifulSoup

url = "https://example.com"
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')
print(soup.title.text)
""",
    requirements=["requests", "beautifulsoup4"],
)
```

### 3. Browser Automation

First start the browser, then:

```python
mission = Mission(
    mission_id="automate_browser",
    code="""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://localhost:9222')
    page = browser.contexts[0].pages[0]
    page.goto('https://github.com')
    print(f"Title: {page.title()}")
""",
    requirements=["playwright"],
    browser_interaction=True,
    keep_alive=True,
)
```

## Configuration

### TaskRunner Options

- `cache_dir`: Directory for caching libraries and environments
- `use_venv`: Whether to use virtual environments (default: True)

### BrowserManager Options

- `user_data_dir`: Directory for browser profile data
- `headless`: Run browser in headless mode (default: False)
- `browser_type`: Browser to use: chromium, firefox, webkit (default: chromium)

### Mission Options

- `mission_id`: Unique identifier (required)
- `code`: Python code to execute (required)
- `requirements`: List of pip packages to install
- `browser_interaction`: Whether script needs browser access
- `keep_alive`: Keep environment after execution
- `timeout`: Maximum execution time in seconds (default: 300)
- `target_device_id`: Specific device to target (for distributed mode)
- `metadata`: Additional metadata dictionary

## Troubleshooting

### Virtual Environment Issues

If venv creation fails:
```bash
python -m ensurepip
python -m pip install --upgrade pip
```

### Playwright Not Found

If browser automation fails:
```bash
pip install playwright
playwright install chromium
```

### Permission Errors

If you get permission errors with cache directory:
```python
import tempfile
task_runner = TaskRunner(cache_dir=Path(tempfile.gettempdir()) / "my_cache")
```

## Next Steps

- Read [TASK_EXECUTOR.md](TASK_EXECUTOR.md) for comprehensive documentation
- Check [API_README.md](API_README.md) for API endpoint details
- Explore [ARCHITECTURE.md](ARCHITECTURE.md) for system architecture
- See [DISTRIBUTED_MODE.md](DISTRIBUTED_MODE.md) for multi-device setup

## Security Notes

⚠️ **Important**: The Task Executor executes arbitrary Python code. Always:
- Validate input code before execution
- Use proper authentication for API endpoints
- Set appropriate resource limits (timeouts)
- Run in isolated environments when possible
- Never expose the API publicly without proper security

## Support

For issues, questions, or contributions, see [CONTRIBUTING.md](CONTRIBUTING.md).
