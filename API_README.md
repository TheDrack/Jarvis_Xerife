# API Server Documentation

This document describes how to use the FastAPI-based headless control interface for the Jarvis Assistant.

## Overview

The API server provides a RESTful interface to control the assistant in headless mode (without a monitor). It's designed to run on servers, containers, or any environment where GUI interaction is not available.

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
