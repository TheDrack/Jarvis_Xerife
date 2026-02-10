# -*- coding: utf-8 -*-
"""
Example Plugin: Hello JARVIS

This is a sample plugin demonstrating JARVIS's auto-extensibility.
Plugins can be added to app/plugins/dynamic/ to extend JARVIS capabilities.
"""

import logging

logger = logging.getLogger(__name__)


def hello_jarvis():
    """Simple function that can be called from JARVIS"""
    return "Hello from a dynamically loaded plugin! 🚀"


def register():
    """
    Optional registration function called when the plugin is loaded.
    Use this to register handlers, initialize resources, etc.
    """
    logger.info("🔌 Example plugin 'Hello JARVIS' registered successfully")
    logger.info(f"   Plugin provides: hello_jarvis() function")


# You can define classes, functions, and any Python code here
class PluginCapability:
    """Example capability class"""
    
    def __init__(self):
        self.name = "Example Plugin Capability"
    
    def execute(self, *args, **kwargs):
        return f"{self.name} executed with args={args}, kwargs={kwargs}"


if __name__ == "__main__":
    # This runs if the plugin is executed directly
    print(hello_jarvis())
