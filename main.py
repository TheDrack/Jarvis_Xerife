#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Jarvis Voice Assistant - Main Entry Point

A modular voice assistant with support for:
- Voice recognition and synthesis
- System automation (PyAutoGUI/Keyboard)
- Web navigation
- Extensible command system
"""

from app.core.engine import JarvisEngine
from app.actions.system_commands import SystemCommands, WebNavigator, CommandProcessor


def main() -> None:
    """Main entry point for Jarvis Assistant"""
    # Initialize components
    engine = JarvisEngine()
    system_commands = SystemCommands()
    web_navigator = WebNavigator(system_commands)
    command_processor = CommandProcessor(system_commands, web_navigator)
    
    # Start the assistant
    try:
        engine.wait_for_wake_word(command_processor.process)
    except KeyboardInterrupt:
        print("\nShutting down Jarvis Assistant...")
        engine.stop()


if __name__ == "__main__":
    main()
