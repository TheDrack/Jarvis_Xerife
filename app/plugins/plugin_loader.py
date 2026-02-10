# -*- coding: utf-8 -*-
"""
Dynamic Plugin Loader

Automatically discovers and loads Python modules from the plugins/dynamic directory.
Enables JARVIS to auto-extend its capabilities by writing new plugin files.
"""

import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Dynamically loads and manages JARVIS plugins.
    
    Plugins are Python modules (.py files) placed in app/plugins/dynamic/.
    Each plugin can define an optional 'register()' function that is called on load.
    """
    
    def __init__(self, plugins_dir: Optional[Path] = None):
        """
        Initialize the plugin loader.
        
        Args:
            plugins_dir: Path to the dynamic plugins directory.
                        Defaults to app/plugins/dynamic
        """
        if plugins_dir is None:
            # Default to app/plugins/dynamic
            # Get the directory where this file is located
            current_file = Path(__file__)
            plugins_dir = current_file.parent / "dynamic"
        
        self.plugins_dir = plugins_dir
        self.loaded_plugins: Dict[str, Any] = {}
        
        # Ensure the plugins directory exists
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Plugin loader initialized: {self.plugins_dir}")
    
    def discover_plugins(self) -> List[Path]:
        """
        Discover all Python files in the plugins directory.
        
        Returns:
            List of paths to plugin files
        """
        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {self.plugins_dir}")
            return []
        
        # Find all .py files except __init__.py
        plugins = [
            f for f in self.plugins_dir.glob("*.py")
            if f.name != "__init__.py" and not f.name.startswith("_")
        ]
        
        logger.info(f"Discovered {len(plugins)} plugin(s): {[p.name for p in plugins]}")
        return plugins
    
    def load_plugin(self, plugin_path: Path) -> Optional[Any]:
        """
        Load a single plugin module.
        
        Args:
            plugin_path: Path to the plugin file
            
        Returns:
            The loaded module or None if loading failed
        """
        plugin_name = plugin_path.stem
        
        try:
            # Create module spec
            spec = importlib.util.spec_from_file_location(
                f"app.plugins.dynamic.{plugin_name}",
                plugin_path
            )
            
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create spec for plugin: {plugin_name}")
                return None
            
            # Load the module
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            
            # Call register function if it exists
            if hasattr(module, "register"):
                logger.info(f"Registering plugin: {plugin_name}")
                module.register()
            
            self.loaded_plugins[plugin_name] = module
            logger.info(f"✓ Loaded plugin: {plugin_name}")
            
            return module
            
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}", exc_info=True)
            return None
    
    def load_all_plugins(self) -> Dict[str, Any]:
        """
        Discover and load all plugins.
        
        Returns:
            Dictionary of loaded plugins (name -> module)
        """
        plugins = self.discover_plugins()
        
        for plugin_path in plugins:
            self.load_plugin(plugin_path)
        
        logger.info(f"Plugin loading complete. {len(self.loaded_plugins)} plugin(s) loaded.")
        return self.loaded_plugins
    
    def reload_plugin(self, plugin_name: str) -> Optional[Any]:
        """
        Reload a specific plugin.
        
        Args:
            plugin_name: Name of the plugin to reload
            
        Returns:
            The reloaded module or None if reload failed
        """
        plugin_path = self.plugins_dir / f"{plugin_name}.py"
        
        if not plugin_path.exists():
            logger.error(f"Plugin not found: {plugin_name}")
            return None
        
        # Remove from loaded plugins if it exists
        if plugin_name in self.loaded_plugins:
            del self.loaded_plugins[plugin_name]
        
        # Reload
        return self.load_plugin(plugin_path)
    
    def create_plugin(self, plugin_name: str, plugin_code: str) -> bool:
        """
        Create a new plugin file.
        
        This enables JARVIS to write new plugins dynamically.
        
        Args:
            plugin_name: Name of the plugin (without .py extension)
            plugin_code: Python code for the plugin
            
        Returns:
            True if plugin was created successfully, False otherwise
        """
        try:
            # Ensure the plugin name is safe
            if not plugin_name.replace("_", "").isalnum():
                logger.error(f"Invalid plugin name: {plugin_name}")
                return False
            
            plugin_path = self.plugins_dir / f"{plugin_name}.py"
            
            # Write the plugin file
            plugin_path.write_text(plugin_code)
            logger.info(f"Created new plugin: {plugin_name}")
            
            # Load the new plugin
            self.load_plugin(plugin_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create plugin {plugin_name}: {e}", exc_info=True)
            return False
    
    def list_plugins(self) -> List[str]:
        """
        List all loaded plugins.
        
        Returns:
            List of plugin names
        """
        return list(self.loaded_plugins.keys())


# Global plugin loader instance
_plugin_loader: Optional[PluginLoader] = None


def get_plugin_loader() -> PluginLoader:
    """
    Get the global plugin loader instance.
    
    Returns:
        The plugin loader instance
    """
    global _plugin_loader
    
    if _plugin_loader is None:
        _plugin_loader = PluginLoader()
    
    return _plugin_loader


def load_plugins():
    """
    Load all plugins from the dynamic directory.
    
    This should be called during JARVIS initialization.
    """
    loader = get_plugin_loader()
    return loader.load_all_plugins()
