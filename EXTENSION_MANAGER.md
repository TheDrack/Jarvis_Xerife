# ExtensionManager - Modern Package Management with UV

## Overview

The ExtensionManager is a modernized package management service that uses `uv` for fast and efficient Python package installation. It extends Jarvis's capabilities by enabling on-demand installation of libraries with intelligent redundancy checking, background installation support, and automatic pre-warming for data tasks.

## Key Features

1. **UV Integration**: Uses the modern `uv` package manager for fast installations with automatic fallback to `pip`
2. **Intelligent Installation**: Checks if libraries already exist before installing to avoid redundancy
3. **Background Tasks**: Supports FastAPI BackgroundTasks for non-blocking installations of heavy libraries
4. **Pre-warming**: Automatically installs recommended libraries (pandas, numpy, matplotlib) for data tasks
5. **Comprehensive Logging**: Reports when new 'skills' (libraries) are successfully installed

## Architecture

### Components

1. **ExtensionManager Service** (`app/application/services/extension_manager.py`)
   - Core service for checking and installing packages using uv or pip
   - Maintains cache of confirmed installations
   - Provides capability name to package name mapping
   - Implements pre-warming for recommended libraries

2. **FastAPI Integration** (`app/adapters/infrastructure/api_server.py`)
   - Three new API endpoints for package management
   - Background task support for async installations
   - Authentication-protected endpoints

3. **Container** (`app/container.py`)
   - Creates and injects ExtensionManager into services
   - Manages the lifecycle of the ExtensionManager instance

## API Endpoints

### POST /v1/extensions/install
Install a package in the background using uv.

**Request:**
```json
{
  "package_name": "pandas"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Installation of 'pandas' started in background",
  "package_name": "pandas",
  "already_installed": false
}
```

### GET /v1/extensions/status/{package_name}
Check if a package is installed.

**Response:**
```json
{
  "package_name": "pandas",
  "installed": true
}
```

### POST /v1/extensions/prewarm
Pre-warm recommended libraries for data tasks (pandas, numpy, matplotlib).

**Response:**
```json
{
  "message": "Pre-warming started in background for: pandas, numpy",
  "libraries": {
    "pandas": false,
    "numpy": false,
    "matplotlib": true
  },
  "all_installed": false
}
```

## Usage

### Basic Usage

```python
from app.application.services import ExtensionManager

# Create an ExtensionManager instance
em = ExtensionManager()

# Install a package (checks if already installed first)
if em.install_package("pandas"):
    import pandas as pd
    # Use pandas
else:
    print("Failed to install pandas")

# Check if a package is installed
if em.is_package_installed("numpy"):
    print("NumPy is available")

# Pre-warm recommended libraries for data tasks
results = em.ensure_recommended_libraries()
print(f"Installation results: {results}")
```

### Using with FastAPI BackgroundTasks

```python
from fastapi import BackgroundTasks, FastAPI
from app.application.services import ExtensionManager

app = FastAPI()
em = ExtensionManager()

@app.post("/install/{package}")
async def install_package(package: str, background_tasks: BackgroundTasks):
    # Install in background to avoid blocking
    background_tasks.add_task(em.install_package, package)
    return {"message": f"Installing {package} in background"}
```

### Automatic Data Task Detection

```python
# When Jarvis detects a data-related task
if em.check_and_install_for_data_task():
    print("Data libraries are ready!")
    # Proceed with data processing
```

## Package Mappings

Some Python packages are imported under different names than their PyPI package names. ExtensionManager handles these mappings automatically:

| Capability Name | Package Name       | Import Name |
|----------------|--------------------|-------------|
| pandas         | pandas             | pandas      |
| numpy          | numpy              | numpy       |
| matplotlib     | matplotlib         | matplotlib  |
| opencv         | opencv-python      | cv2         |
| cv2            | opencv-python      | cv2         |
| bs4            | beautifulsoup4     | bs4         |
| sklearn        | scikit-learn       | sklearn     |
| playwright     | playwright         | playwright  |

## Recommended Libraries

The ExtensionManager maintains a list of recommended libraries for data tasks:
- **pandas**: Data manipulation and analysis
- **numpy**: Numerical computing
- **matplotlib**: Data visualization

These libraries are automatically installed when:
1. Using the `ensure_recommended_libraries()` method
2. Using the `check_and_install_for_data_task()` method
3. Calling the `/v1/extensions/prewarm` API endpoint

## Configuration

### UV vs PIP

The ExtensionManager automatically detects if `uv` is available and uses it for faster installations. If `uv` is not available, it falls back to `pip`:

```python
# Try to use uv (will fallback to pip if not available)
em = ExtensionManager(use_uv=True)

# Force pip usage
em = ExtensionManager(use_uv=False)
```

### Installation Timeout

The package installation timeout is configured via the `INSTALL_TIMEOUT` constant:

```python
class ExtensionManager:
    # Installation timeout in seconds (5 minutes by default)
    INSTALL_TIMEOUT = 300
```

## Testing

The ExtensionManager includes comprehensive test coverage:

```bash
# Run ExtensionManager tests
pytest tests/application/test_extension_manager.py -v

# Run all application tests
pytest tests/application/ -v
```

## Demo

A demonstration script is provided to show the feature in action:

```bash
python demo_extension_manager.py
```

## Logging

The ExtensionManager provides detailed logging for all operations:

- **INFO**: Package installation status, successful installations
- **WARNING**: Fallback to pip when uv is not available
- **ERROR**: Installation failures, timeout errors
- **DEBUG**: Detailed installation output, redundancy checks

Example log output:
```
2026-02-07 14:58:07 - ExtensionManager initialized (using uv)
2026-02-07 14:58:10 - Package 'requests' is already installed, skipping redundant installation
2026-02-07 14:58:15 - Installing package 'pandas' via uv...
2026-02-07 14:58:45 - ✅ Successfully installed new skill (library): 'pandas'
```

## Differences from DependencyManager

While the ExtensionManager is similar to the existing DependencyManager, it has several key improvements:

| Feature | DependencyManager | ExtensionManager |
|---------|------------------|------------------|
| Package Manager | pip only | uv with pip fallback |
| API Endpoints | None | 3 RESTful endpoints |
| Background Tasks | No | Yes (FastAPI BackgroundTasks) |
| Pre-warming | No | Yes (recommended libraries) |
| Data Task Detection | No | Yes (automatic) |
| Package Mappings | 7 mappings | 10+ mappings |

## Security Considerations

1. **Package Source**: Packages are installed from PyPI using uv or pip
2. **Timeout Protection**: 5-minute timeout prevents indefinite hangs
3. **Error Handling**: Comprehensive error handling for network issues, permission errors, etc.
4. **Authentication**: API endpoints are protected with OAuth2 authentication
5. **Logging**: All installation attempts are logged for audit purposes

## Performance

1. **UV Speed**: When available, uv provides significantly faster package installation than pip
2. **Caching**: Successfully verified packages are cached to avoid redundant checks
3. **Lazy Installation**: Packages are only installed when actually needed
4. **Non-blocking**: Background task support prevents blocking the main application
5. **Redundancy Check**: Avoids redundant installations by checking first

## Future Enhancements

1. **Version Control**: Specify required package versions
2. **Offline Mode**: Support for offline package installation from local cache
3. **Dependency Trees**: Automatic installation of package dependencies
4. **Virtual Environments**: Isolated package installations per capability
5. **Update Management**: Automatic updates for installed packages
6. **Requirements Export**: Export installed packages to requirements.txt

## Troubleshooting

### UV Not Available

If uv is not installed, the ExtensionManager automatically falls back to pip:
```
WARNING - uv not available, falling back to pip for package installation
```

To install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Package Installation Fails

Check the logs for error details. Common issues:
- No internet connection
- Insufficient disk space
- Permission errors (may require elevated privileges)
- PyPI package not found

### Background Tasks Not Working

Ensure you're using FastAPI's BackgroundTasks correctly:
```python
from fastapi import BackgroundTasks

@app.post("/endpoint")
async def endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(em.install_package, "package_name")
```

## Integration with Jarvis

The ExtensionManager is automatically integrated with Jarvis through the dependency injection container:

```python
# In serve.py
container = create_edge_container()
extension_manager = container.extension_manager
app = create_api_server(assistant, extension_manager)
```

This makes it available to all API endpoints and services that need it.
