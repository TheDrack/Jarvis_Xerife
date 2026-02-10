# JARVIS Dynamic Plugin System

## Overview

This directory contains JARVIS's dynamic plugin system, enabling **auto-extensibility**. JARVIS can write new Python modules here to extend its own capabilities.

## Philosophy

> "JARVIS is a union of this repository (DNA), GitHub Agents (metabolism), the DB (memory), Render (heart), with integration and plugin capabilities to scale to any device or technology."  
> — @TheDrack

JARVIS should not depend on a single database, LLM, or technology. Whatever is available becomes part of JARVIS.

## Directory Structure

```
app/plugins/
├── __init__.py              # Plugin package initialization
├── plugin_loader.py         # Dynamic plugin loader service
└── dynamic/                 # Auto-loaded plugins directory
    ├── __init__.py
    └── example_plugin.py    # Sample plugin
```

## How It Works

1. **Auto-Loading**: When JARVIS starts, `main.py` calls `load_plugins()` which automatically discovers and loads all `.py` files in `app/plugins/dynamic/`

2. **Registration**: Plugins can define an optional `register()` function that is called when the plugin is loaded

3. **Dynamic Creation**: JARVIS can write new plugins at runtime using `PluginLoader.create_plugin(name, code)`

## Creating a Plugin

### Manual Creation

Create a new `.py` file in `app/plugins/dynamic/`:

```python
# my_custom_plugin.py

import logging

logger = logging.getLogger(__name__)

def my_function():
    """Your custom function"""
    return "Hello from my plugin!"

def register():
    """Optional: Called when plugin is loaded"""
    logger.info("My custom plugin registered!")
```

### Programmatic Creation

JARVIS can create plugins dynamically:

```python
from app.plugins.plugin_loader import get_plugin_loader

loader = get_plugin_loader()

plugin_code = '''
def dynamic_capability():
    return "I was created by JARVIS!"

def register():
    print("Dynamic plugin loaded!")
'''

loader.create_plugin("dynamic_capability", plugin_code)
```

## Plugin API

### PluginLoader Methods

```python
from app.plugins.plugin_loader import get_plugin_loader

loader = get_plugin_loader()

# Load all plugins
plugins = loader.load_all_plugins()

# Create a new plugin
loader.create_plugin("my_plugin", plugin_code)

# Reload a plugin
loader.reload_plugin("my_plugin")

# List loaded plugins
plugin_names = loader.list_plugins()
```

## Integration with Capability Manager

Plugins can enhance JARVIS capabilities:

1. **Detect Capability**: Plugin adds detection logic to CapabilityManager
2. **Implement Capability**: Plugin provides the actual implementation
3. **Register Capability**: Plugin updates the capability status in the database

Example:

```python
# auto_capability_plugin.py

from app.application.services.capability_manager import CapabilityManager

def register():
    # Register this plugin as implementing capability #50
    # (Orchestrate multiple agents simultaneously)
    print("Orchestration capability registered!")

class MultiAgentOrchestrator:
    """Implementation of capability #50"""
    
    def orchestrate(self, agents):
        # Your implementation here
        pass
```

## Use Cases

### 1. API Integration Plugins

When JARVIS needs to integrate with a new API:

```python
# stripe_integration.py

import stripe

def process_payment(amount, currency="usd"):
    # Stripe payment logic
    pass

def register():
    # Set up Stripe with API key from environment
    stripe.api_key = os.getenv("STRIPE_API_KEY")
```

### 2. Custom Actions

Add new actions JARVIS can perform:

```python
# custom_actions.py

def send_telegram_message(chat_id, message):
    # Telegram integration
    pass

def send_email(to, subject, body):
    # Email integration
    pass
```

### 3. Data Processing

Add specialized data processing:

```python
# data_analyzer.py

import pandas as pd

def analyze_csv(file_path):
    df = pd.read_csv(file_path)
    return df.describe()
```

## Security Considerations

⚠️ **Important**: Since JARVIS can write code to this directory:

1. **Permissions**: Ensure the `dynamic/` directory has appropriate write permissions
2. **Validation**: Consider implementing code validation before loading plugins
3. **Sandboxing**: In production, consider running plugins in isolated environments
4. **Audit**: Log all plugin creation and loading activities

## Plugin Best Practices

1. **Naming**: Use descriptive, snake_case names (e.g., `github_integration.py`)
2. **Dependencies**: Document any required packages in the plugin file
3. **Error Handling**: Use try-except blocks for robust plugins
4. **Logging**: Use Python's logging module for debugging
5. **Registration**: Implement `register()` for initialization logic
6. **Documentation**: Add docstrings to functions and classes

## Example: Complete Plugin

```python
# weather_plugin.py
"""
Weather Plugin for JARVIS

Provides weather information using OpenWeatherMap API.
Requires: OPENWEATHER_API_KEY environment variable
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

def get_weather(city):
    """
    Get current weather for a city.
    
    Args:
        city: City name
        
    Returns:
        Weather information dictionary
    """
    if not API_KEY:
        return {"error": "API key not configured"}
    
    try:
        params = {
            "q": city,
            "appid": API_KEY,
            "units": "metric"
        }
        response = requests.get(BASE_URL, params=params)
        response.raise_for_status()
        return response.json()
    
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return {"error": str(e)}

def register():
    """Register the weather plugin"""
    if API_KEY:
        logger.info("✓ Weather plugin registered with API key")
    else:
        logger.warning("⚠ Weather plugin registered without API key")
```

## Monitoring and Debugging

Check which plugins are loaded:

```python
from app.plugins.plugin_loader import get_plugin_loader

loader = get_plugin_loader()
print(f"Loaded plugins: {loader.list_plugins()}")
```

View plugin loading in logs:

```
INFO:app.plugins.plugin_loader:Discovered 3 plugin(s): ['example_plugin.py', ...]
INFO:app.plugins.plugin_loader:✓ Loaded plugin: example_plugin
INFO:app.plugins.plugin_loader:Plugin loading complete. 3 plugin(s) loaded.
```

## Future Enhancements

- **Plugin Marketplace**: Share plugins with the JARVIS community
- **Version Control**: Track plugin versions and updates
- **Hot Reload**: Reload plugins without restarting JARVIS
- **Plugin Dependencies**: Manage dependencies between plugins
- **Plugin Sandboxing**: Run untrusted plugins in isolated environments

## Contributing

To add a new plugin to the JARVIS ecosystem:

1. Create your plugin in `app/plugins/dynamic/`
2. Test it locally
3. Document it in this README
4. Submit a PR with your plugin

---

**JARVIS Auto-Extensibility: Making AI truly autonomous** 🤖✨
