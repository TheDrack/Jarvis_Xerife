# DependencyManager - On-Demand Capabilities System

## Overview

The DependencyManager is a service that enables Jarvis to automatically install required Python packages at runtime. This allows the assistant to extend its capabilities on-demand without requiring all possible dependencies to be pre-installed.

## Architecture

### Components

1. **DependencyManager Service** (`app/application/services/dependency_manager.py`)
   - Core service for checking and installing packages
   - Uses subprocess to call pip for package installation
   - Maintains cache of confirmed installations
   - Provides capability name to package name mapping

2. **AssistantService Integration** (`app/application/services/assistant_service.py`)
   - Receives DependencyManager via dependency injection
   - Calls `ensure_capability()` before executing commands that need special libraries
   - Returns proper error responses if dependencies can't be installed

3. **Container** (`app/container.py`)
   - Creates and injects DependencyManager into AssistantService
   - Manages the lifecycle of the DependencyManager instance

4. **Build Configuration** (`build_config.py`)
   - Includes `ensurepip`, `setuptools`, and `pip` in PyInstaller hidden imports
   - Ensures the embedded Python in .exe can install packages at runtime

## Usage

### Basic Usage

```python
from app.application.services import DependencyManager

# Create a DependencyManager instance
dm = DependencyManager()

# Ensure a capability is available (will install if needed)
if dm.ensure_capability("pandas"):
    import pandas as pd
    # Use pandas
else:
    print("Failed to ensure pandas capability")

# Check availability without installing
if dm.is_capability_available("opencv"):
    print("OpenCV is available")
```

### Capability Mappings

Some Python packages are imported under different names than their PyPI package names. DependencyManager handles these mappings automatically:

| Capability Name | Package Name       | Import Name |
|----------------|-------------------|-------------|
| pandas         | pandas            | pandas      |
| playwright     | playwright        | playwright  |
| opencv         | opencv-python     | cv2         |
| cv2            | opencv-python     | cv2         |
| bs4            | beautifulsoup4    | bs4         |
| numpy          | numpy             | numpy       |
| requests       | requests          | requests    |

### Integration with AssistantService

The AssistantService automatically checks for required capabilities before executing commands:

```python
def _execute_command(self, command_type: CommandType, params: dict) -> Response:
    # Check for dependencies before executing complex commands
    required_capability = self._get_required_capability(command_type, params)
    if required_capability:
        if not self.dependency_manager.ensure_capability(required_capability):
            return Response(
                success=False,
                message=f"Failed to ensure required capability: {required_capability}",
                error="MISSING_DEPENDENCY",
            )
    # ... execute command
```

## Extending the System

### Adding New Capability Mappings

To add support for a new library, update the `CAPABILITY_PACKAGES` dictionary in `DependencyManager`:

```python
CAPABILITY_PACKAGES: Dict[str, str] = {
    # ... existing mappings ...
    "new_capability": "pypi-package-name",
}
```

### Adding Command-Specific Capabilities

To make certain commands automatically install dependencies, update `_get_required_capability()` in `AssistantService`:

```python
def _get_required_capability(self, command_type: CommandType, params: dict) -> Optional[str]:
    # Example: Data analysis commands need pandas
    if command_type == CommandType.ANALYZE_DATA:
        return "pandas"
    
    # Example: Web scraping needs playwright
    if command_type == CommandType.WEB_SCRAPE:
        return "playwright"
    
    # Example: Image processing needs opencv
    if params.get("process_image"):
        return "opencv"
    
    return None
```

## Configuration

### Installation Timeout

The package installation timeout can be configured via the `INSTALL_TIMEOUT` constant:

```python
class DependencyManager:
    # Installation timeout in seconds (5 minutes by default)
    INSTALL_TIMEOUT = 300
```

### Build Configuration

For standalone .exe deployment, ensure these imports are included in `build_config.py`:

```python
HIDDEN_IMPORTS = [
    # ... other imports ...
    
    # Package management for on-demand installation
    'ensurepip',
    'setuptools',
    'pip',
    'pip._internal',
    'pip._vendor',
]
```

## Testing

The DependencyManager includes comprehensive test coverage:

```bash
# Run DependencyManager tests
pytest tests/application/test_dependency_manager.py -v

# Run all application tests
pytest tests/application/ -v
```

## Demo

A demonstration script is provided to show the feature in action:

```bash
python demo_dependency_manager.py
```

## Security Considerations

1. **Package Source**: Packages are installed from PyPI using pip
2. **Timeout Protection**: 5-minute timeout prevents indefinite hangs
3. **Error Handling**: Comprehensive error handling for network issues, permission errors, etc.
4. **Logging**: All installation attempts are logged for audit purposes

## Performance

1. **Caching**: Successfully verified packages are cached to avoid redundant checks
2. **Lazy Installation**: Packages are only installed when actually needed
3. **Non-blocking**: Failed installations don't crash the application

## Troubleshooting

### Package Installation Fails

Check the logs for error details:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Common issues:
- No internet connection
- Insufficient disk space
- Permission errors (may require elevated privileges)
- PyPI package not found

### Embedded Python Issues

If running from a PyInstaller .exe and packages can't be installed:
1. Verify `ensurepip` is included in hidden imports
2. Check that the Python environment is writable
3. Ensure the .exe has internet access

## Future Enhancements

1. **Version Control**: Specify required package versions
2. **Offline Mode**: Support for offline package installation from local cache
3. **Dependency Trees**: Automatic installation of package dependencies
4. **Virtual Environments**: Isolated package installations per capability
5. **Update Management**: Automatic updates for installed packages
