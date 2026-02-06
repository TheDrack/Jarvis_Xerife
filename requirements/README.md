# Requirements Files

This directory contains separated dependency files for different deployment scenarios.

## Files

### `core.txt` - Cloud-Ready Core
Core dependencies with **no hardware requirements**:
- Pydantic and pydantic-settings for configuration
- FastAPI and Uvicorn for REST API server
- SQLModel and psycopg2-binary for database (PostgreSQL/SQLite)
- python-jose and passlib for authentication and security
- Can run in headless Linux environment
- No display, audio, or input device dependencies

**Use for**: Cloud deployment, CI/CD, API servers, core business logic development

```bash
pip install -r requirements/core.txt
```

### `edge.txt` - Edge Deployment
Edge dependencies including hardware automation:
- Includes `core.txt`
- PyAutoGUI (screen automation)
- SpeechRecognition (voice input)
- pyttsx3 (text-to-speech)
- pynput (keyboard/mouse control)
- pyaudio (audio input/output)
- google-generativeai (LLM integration)
- pandas and openpyxl (data processing utilities)

**Requires**: Display server, audio drivers, input devices

**Use for**: Local development, edge devices with hardware

```bash
pip install -r requirements/edge.txt
```

### `dev.txt` - Development Tools
Development and testing dependencies:
- Includes `core.txt`
- pytest, pytest-cov, pytest-mock, pytest-asyncio (testing framework)
- mypy and types-requests (type checking)
- black, flake8, isort (code formatting and linting)
- ipython and ipdb (development tools)

**Use for**: Development, testing, code quality checks

```bash
pip install -r requirements/dev.txt
```

### `prod-edge.txt` - Production Edge
Full edge deployment with optional services:
- Includes `edge.txt`
- Optional: Airflow, FastAPI
- Production-ready edge configuration

**Use for**: Production edge devices

```bash
pip install -r requirements/prod-edge.txt
```

### `prod-cloud.txt` - Production Cloud
Cloud deployment without hardware:
- Includes `core.txt`
- Optional: FastAPI, cloud SDKs
- Headless production configuration

**Use for**: Cloud/container deployments, APIs

```bash
pip install -r requirements/prod-cloud.txt
```

## Deployment Examples

### Local Development (Edge)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements/edge.txt
python main.py
```

### Cloud Deployment
```bash
pip install -r requirements/core.txt
# Then configure your API server or cloud service
```

### Development/Testing
```bash
pip install -r requirements/dev.txt
pytest tests/
```

### Docker Edge
```dockerfile
COPY requirements/edge.txt requirements/core.txt requirements/
RUN pip install -r requirements/edge.txt
```

### Docker Cloud
```dockerfile
COPY requirements/core.txt requirements/
RUN pip install -r requirements/core.txt
```

## Dependency Philosophy

1. **Core First**: Always starts with cloud-ready core
2. **Layer Dependencies**: Each file builds on previous layers
3. **Optional Features**: Use comments for optional dependencies
4. **Minimal Base**: Keep core.txt as small as possible
5. **Explicit Versions**: Pin major versions, allow minor updates

## Adding New Dependencies

### For Core (Cloud-Ready)
Only add if:
- Pure Python library
- No OS-specific requirements
- No hardware dependencies
- Required for business logic

### For Edge (Hardware)
Add if:
- Requires display server
- Needs audio/video drivers
- System automation
- Local file system operations

### For Dev
Add if:
- Development tool only
- Not required in production
- Testing or code quality
