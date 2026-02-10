# API Server Documentation

This document describes how to use the FastAPI-based headless control interface for the Jarvis Assistant.

## Overview

The API server provides a RESTful interface to control the assistant in headless mode (without a monitor). It's designed to run on servers, containers, or any environment where GUI interaction is not available.

## 🌐 Web Interface

In addition to the REST API, Jarvis provides a **Stark Industries-themed web interface** accessible at the root endpoint (`/`).

### Features
- 🔐 **Secure Login**: OAuth2 JWT authentication
- 🎤 **Voice Commands**: Built-in speech-to-text (Portuguese BR)
- 💻 **Terminal Interface**: Execute commands with real-time feedback
- ⚡ **Activity Monitoring**: Auto-logout after 30 minutes of inactivity
- 🎨 **Stark Industries Theme**: Glowing cyan UI with dark gradients

### Screenshots

#### Login Screen
![J.A.R.V.I.S. Login](https://github.com/user-attachments/assets/59f612f3-b6c7-4cce-8a0d-020cec716dac)

#### Main Interface with Voice Input
![J.A.R.V.I.S. Interface](https://github.com/user-attachments/assets/312ea9ad-8b84-4cbc-84fd-06d69e06c35c)

### Accessing the Interface

1. Start the API server: `python serve.py`
2. Navigate to `http://localhost:8000` in your browser
3. Login with default credentials: `admin` / `admin123`
4. Use text commands or click the microphone button 🎤 for voice input

### Voice Recognition

The voice input feature uses the browser's Web Speech API and supports:
- Portuguese Brazilian (`pt-BR`) language
- Real-time speech-to-text conversion
- Visual feedback during recording
- Automatic text insertion into command input

**Note**: Voice recognition requires HTTPS in production or localhost for development. Some browsers may not support this feature.

## Quick Start

### Installation

Install the API dependencies:

```bash
pip install -r requirements/api.txt
# or
pip install fastapi uvicorn[standard]
```

### Starting the Server

Run the server using the `serve.py` entry point:

```bash
python serve.py
```

The server will start on `http://0.0.0.0:8000` by default.

### Configuration

You can configure the server using environment variables:

- `API_HOST`: Host to bind to (default: `0.0.0.0`)
- `PORT`: Port to listen on (standard for Render and cloud platforms, default: `8000`)
- `API_PORT`: Alternative port variable for backward compatibility (default: `8000`)
- `DISPLAY`: Set to empty string for headless mode
- `USE_LLM`: Use LLM-based command interpretation (default: `false`)

**Note**: The server prioritizes `PORT` over `API_PORT` to be compatible with cloud platforms like Render.com that automatically set the `PORT` environment variable.

Example:

```bash
# Local development with custom port
API_HOST=127.0.0.1 API_PORT=8888 python serve.py

# Or using PORT (Render-compatible)
PORT=8888 python serve.py
```

## API Endpoints

### Health Check

Check if the server is running.

```
GET /health
```

**Response:**

```json
{
  "status": "healthy"
}
```

### System Status

Get the current system status and configuration.

```
GET /v1/status
```

**Response:**

```json
{
  "app_name": "Jarvis Assistant",
  "version": "1.0.0",
  "is_active": false,
  "wake_word": "xerife",
  "language": "pt-BR"
}
```

### Execute Command

Execute a command and get the result.

```
POST /v1/execute
```

**Request Body:**

```json
{
  "command": "escreva hello world"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Typed: hello world",
  "data": null,
  "error": null
}
```

**Error Response:**

```json
{
  "success": false,
  "message": "Unknown command: invalid",
  "data": null,
  "error": "UNKNOWN_COMMAND"
}
```

### Send Message (Simplified Interface)

Send a simple message to the assistant without complex JSON structures.

This is a user-friendly alternative to `/v1/execute` that accepts natural language messages in a simplified format.

```
POST /v1/message
```

**Request Body:**

```json
{
  "text": "What's the weather like today?"
}
```

**Response:**

```json
{
  "success": true,
  "response": "I apologize, but I don't have access to real-time weather information.",
  "error": null
}
```

**Error Response:**

```json
{
  "success": false,
  "response": "",
  "error": "Internal server error: Connection timeout"
}
```

**Why use `/v1/message` instead of `/v1/execute`?**

- Simpler JSON structure (just `text` instead of `command`)
- More intuitive for chat-like interactions
- Returns response text directly without nested data structures
- Perfect for building conversational interfaces

**When to use `/v1/execute` instead?**

- When you need detailed metadata and execution context
- When you need the structured `data` field in responses
- For programmatic command execution with specific error codes

### Command History

Get recent command execution history.

```
GET /v1/history?limit=5
```

**Query Parameters:**

- `limit`: Maximum number of commands to return (default: 5, max: 50)

**Response:**

```json
{
  "commands": [
    {
      "command": "escreva hello",
      "timestamp": "2024-01-01T00:00:00Z",
      "success": true,
      "message": "Typed: hello"
    },
    {
      "command": "aperte enter",
      "timestamp": "2024-01-01T00:00:01Z",
      "success": true,
      "message": "Pressed: enter"
    }
  ],
  "total": 2
}
```

## Interactive API Documentation

FastAPI provides automatic interactive API documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`

## Example Usage

### Using curl

```bash
# Execute a command
curl -X POST http://localhost:8000/v1/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "escreva hello world"}'

# Get status
curl http://localhost:8000/v1/status

# Get history
curl http://localhost:8000/v1/history?limit=10
```

### Using Python requests

```python
import requests

# Execute a command
response = requests.post(
    "http://localhost:8000/v1/execute",
    json={"command": "escreva hello world"}
)
print(response.json())

# Get status
response = requests.get("http://localhost:8000/v1/status")
print(response.json())

# Get history
response = requests.get("http://localhost:8000/v1/history?limit=5")
print(response.json())
```

### Using httpie

```bash
# Execute a command
http POST localhost:8000/v1/execute command="escreva hello world"

# Get status
http GET localhost:8000/v1/status

# Get history
http GET localhost:8000/v1/history limit==10
```

## Headless Safety

The server is designed to run safely in headless environments:

1. **No GUI Dependencies**: The server doesn't require a display server
2. **Error Handling**: Errors are logged and returned via API, not shown in GUI dialogs
3. **Graceful Degradation**: Missing hardware adapters (voice, automation) are detected and logged, but the API continues to work
4. **Environment Variables**: The `DISPLAY` environment variable is automatically managed

## Security Considerations

⚠️ **Important**: This API has no authentication by default. Consider:

1. Running behind a reverse proxy with authentication (nginx, traefik)
2. Using a firewall to restrict access to trusted networks
3. Adding authentication middleware if exposing to the internet
4. Using HTTPS in production

## Docker Deployment

The API server can be deployed in a Docker container:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements/api.txt requirements/core.txt requirements/
RUN pip install -r requirements/api.txt

COPY app/ app/
COPY serve.py .

ENV DISPLAY=""
ENV API_HOST=0.0.0.0
# PORT can be overridden at runtime (e.g., by Render)
ENV PORT=8000

CMD ["python", "serve.py"]
```

Build and run:

```bash
docker build -t jarvis-api .
docker run -p 8000:8000 jarvis-api
```

## Troubleshooting

### Server won't start

- Check that all dependencies are installed: `pip install -r requirements/api.txt`
- Verify the port is not already in use
- Check logs for detailed error messages

### Commands fail to execute

- Check that the command syntax is correct (see main documentation)
- Review the error message and error code in the response
- Check if hardware adapters are available (voice, automation)
- Review server logs for detailed error traces

### History is empty

- Execute at least one command first
- History is kept in memory and resets when the server restarts
- Maximum history size is 100 commands

## Development

### Running Tests

```bash
# Run API tests
pytest tests/adapters/infrastructure/test_api_server.py -v

# Run with coverage
pytest tests/adapters/infrastructure/test_api_server.py --cov=app/adapters/infrastructure/api_server
```

### Code Quality

```bash
# Format code
black serve.py app/adapters/infrastructure/api_*.py

# Lint code
flake8 serve.py app/adapters/infrastructure/api_*.py --max-line-length=100

# Type check
mypy serve.py app/adapters/infrastructure/api_*.py
```

## Mission Execution Endpoints

The Task Executor provides serverless function execution capabilities for distributed Workers. See [TASK_EXECUTOR.md](TASK_EXECUTOR.md) for comprehensive documentation.

### Execute Mission

Execute a Python script on a Worker device with automatic dependency management.

**Endpoint:** `POST /v1/missions/execute`

**Authentication:** Required (Bearer token)

**Request Body:**

```json
{
  "mission_id": "mission_001",
  "code": "import requests\nresponse = requests.get('https://api.github.com')\nprint(response.status_code)",
  "requirements": ["requests"],
  "browser_interaction": false,
  "keep_alive": false,
  "target_device_id": 123,
  "timeout": 300,
  "metadata": {}
}
```

**Response:**

```json
{
  "mission_id": "mission_001",
  "success": true,
  "stdout": "200\n",
  "stderr": "",
  "exit_code": 0,
  "execution_time": 1.234,
  "error": null,
  "metadata": {}
}
```

### Control Browser

Control the persistent Playwright browser instance.

**Endpoint:** `POST /v1/browser/control`

**Authentication:** Required (Bearer token)

**Request Body:**

```json
{
  "operation": "start",
  "port": 9222
}
```

**Operations:** `start`, `stop`, `status`

### Record Automation

Start recording browser automation with Playwright codegen.

**Endpoint:** `POST /v1/browser/record`

**Authentication:** Required (Bearer token)

**Request Body:**

```json
{
  "output_file": "/path/to/save/skill.py"
}
```

For detailed examples and advanced usage, see [TASK_EXECUTOR.md](TASK_EXECUTOR.md).

## Self-Healing Orchestrator API

The Self-Healing Orchestrator enables Jarvis to manage its own development lifecycle and automatically fix issues.

### ThoughtLog Management

ThoughtLogs store Jarvis's internal reasoning and problem-solving process, separate from user interactions.

#### Create ThoughtLog

Create a new thought log entry to track internal reasoning.

```
POST /v1/thoughts
```

**Request Body:**

```json
{
  "mission_id": "fix_ci_build_123",
  "session_id": "session_abc",
  "status": "internal_monologue",
  "thought_process": "Analyzing CI build failure. Logs show dependency conflict.",
  "problem_description": "CI build failed due to version mismatch",
  "solution_attempt": "Updating requirements.txt to use compatible versions",
  "success": false,
  "error_message": "Build still failing after dependency update",
  "context_data": {
    "build_log_url": "https://github.com/...",
    "error_type": "ImportError"
  }
}
```

**Response:**

```json
{
  "id": 42,
  "mission_id": "fix_ci_build_123",
  "session_id": "session_abc",
  "status": "internal_monologue",
  "thought_process": "Analyzing CI build failure...",
  "problem_description": "CI build failed due to version mismatch",
  "solution_attempt": "Updating requirements.txt...",
  "success": false,
  "error_message": "Build still failing...",
  "retry_count": 1,
  "requires_human": false,
  "escalation_reason": "",
  "created_at": "2024-01-01T12:00:00Z"
}
```

#### Get Mission ThoughtLogs

Retrieve all thought logs for a specific mission.

```
GET /v1/thoughts/mission/{mission_id}
```

**Response:**

```json
{
  "logs": [
    {
      "id": 40,
      "mission_id": "fix_ci_build_123",
      "session_id": "session_abc",
      "status": "internal_monologue",
      "thought_process": "First attempt: checking logs",
      "success": false,
      "retry_count": 0,
      "created_at": "2024-01-01T11:00:00Z"
    },
    {
      "id": 41,
      "mission_id": "fix_ci_build_123",
      "session_id": "session_abc",
      "thought_process": "Second attempt: updating dependencies",
      "success": false,
      "retry_count": 1,
      "created_at": "2024-01-01T11:30:00Z"
    }
  ],
  "total": 2
}
```

#### Get Pending Escalations

Retrieve missions that require human intervention (failed 3+ times).

```
GET /v1/thoughts/escalations
```

**Response:**

```json
{
  "logs": [
    {
      "id": 43,
      "mission_id": "fix_ci_build_456",
      "retry_count": 3,
      "requires_human": true,
      "escalation_reason": "Auto-correction failed 3 times. Human intervention required.",
      "created_at": "2024-01-01T13:00:00Z"
    }
  ],
  "total": 1
}
```

#### Get Consolidated Log

Generate a consolidated log of all attempts for a mission.

```
GET /v1/thoughts/mission/{mission_id}/consolidated
```

**Response:**

```json
{
  "mission_id": "fix_ci_build_123",
  "consolidated_log": "=== Consolidated Log for Mission: fix_ci_build_123 ===\nTotal Attempts: 3\nStatus: ESCALATED TO HUMAN\n\n--- Attempt 1 (2024-01-01T11:00:00Z) ---\nProblem: CI build failed...\nReasoning: Checking logs...\nResult: FAILED\n..."
}
```

### GitHub Worker Operations

GitHub Worker provides auto-evolution capabilities through GitHub CLI integration.

#### Execute GitHub Operation

Perform GitHub operations like creating branches, submitting PRs, or checking CI status.

```
POST /v1/github/worker
```

**Request Body (Create Branch):**

```json
{
  "operation": "create_branch",
  "branch_name": "feature/auto-fix-ci-123"
}
```

**Request Body (Submit PR):**

```json
{
  "operation": "submit_pr",
  "pr_title": "Auto-fix: Resolve CI dependency conflict",
  "pr_body": "This PR was automatically generated to fix CI build failure #123.\n\nChanges:\n- Updated requirements.txt\n- Fixed version conflicts"
}
```

**Request Body (Fetch CI Status):**

```json
{
  "operation": "fetch_ci_status",
  "run_id": 12345
}
```

**Response:**

```json
{
  "success": true,
  "message": "CI status: completed, conclusion: failure",
  "data": {
    "status": "completed",
    "conclusion": "failure",
    "failed": true,
    "run_id": 12345
  }
}
```

#### Auto-Heal CI Failure

Automatically attempt to fix a CI failure by analyzing logs and applying patches.

```
POST /v1/github/ci-heal/{run_id}?mission_id={mission_id}
```

**Response (Success):**

```json
{
  "success": true,
  "message": "Fix applied successfully",
  "logs_analyzed": 5432
}
```

**Response (Escalation Required):**

```json
{
  "success": false,
  "requires_human": true,
  "message": "Auto-correction failed 3 times. Escalating to Commander.",
  "consolidated_log": "=== Consolidated Log for Mission... ==="
}
```

### Self-Healing Workflow Example

Here's how the self-healing orchestrator works in practice:

1. **CI Failure Detection**: GitHub Actions workflow fails
2. **Auto-Heal Trigger**: Call `/v1/github/ci-heal/{run_id}`
3. **Log Analysis**: System downloads and analyzes CI logs
4. **Internal Reasoning**: Creates ThoughtLog with analysis (INTERNAL_MONOLOGUE)
5. **Solution Generation**: Generates fix based on error patterns
6. **Patch Application**: Uses `file_write` to apply code changes
7. **Retry**: Commits, pushes, and triggers new CI run
8. **Escalation**: After 3 failures, escalates to human via `/v1/thoughts/escalations`

### Python Example: Self-Healing Integration

```python
import requests

class JarvisSelfHealing:
    def __init__(self, api_base_url, token):
        self.base_url = api_base_url
        self.headers = {"Authorization": f"Bearer {token}"}
    
    def monitor_and_heal_ci(self, run_id, mission_id):
        """Monitor CI run and auto-heal if it fails"""
        
        # Check CI status
        response = requests.post(
            f"{self.base_url}/v1/github/worker",
            json={"operation": "fetch_ci_status", "run_id": run_id},
            headers=self.headers
        )
        
        status_data = response.json()
        
        if status_data["data"]["failed"]:
            print(f"CI run {run_id} failed. Attempting auto-heal...")
            
            # Attempt auto-heal
            heal_response = requests.post(
                f"{self.base_url}/v1/github/ci-heal/{run_id}",
                params={"mission_id": mission_id},
                headers=self.headers
            )
            
            heal_data = heal_response.json()
            
            if heal_data.get("requires_human"):
                print("❌ Auto-heal failed after 3 attempts")
                print("📋 Consolidated log:")
                print(heal_data["consolidated_log"])
                
                # Notify commander
                self.notify_commander(mission_id)
            else:
                print("✅ Auto-heal applied successfully")
        else:
            print(f"✅ CI run {run_id} passed")
    
    def notify_commander(self, mission_id):
        """Notify human commander about escalation"""
        # Get consolidated log
        response = requests.get(
            f"{self.base_url}/v1/thoughts/mission/{mission_id}/consolidated",
            headers=self.headers
        )
        
        log_data = response.json()
        
        # Send notification (Slack, email, etc.)
        print(f"🚨 COMMANDER ALERT: Mission {mission_id} requires intervention")
        print(log_data["consolidated_log"])

# Usage
jarvis = JarvisSelfHealing("http://localhost:8000", "your-token")
jarvis.monitor_and_heal_ci(run_id=12345, mission_id="fix_build_123")
```
