#-*- coding:utf-8 -*-
"""
Example usage of the JarvisEngine class.

This file demonstrates how to use the refactored voice logic
from the JarvisEngine class.
"""

from app.core.engine import JarvisEngine


def main():
    """Main function demonstrating JarvisEngine usage."""
    # Initialize the engine
    engine = JarvisEngine()
    
    # Example 1: Using the falar (speak) method
    engine.falar("Olá, eu sou o Jarvis!")
    
    # Example 2: Using Ligar_microfone to listen for commands
    # This will return Optional[str] - either a command or None
    comando = engine.Ligar_microfone()
    if comando:
        print(f"Comando recebido: {comando}")
    else:
        print("Nenhum comando recebido ou comando cancelado")
    
    # Example 3: Using chamarAXerife for the main assistant loop
    # This runs the main voice assistant loop with wake word detection
    # engine.chamarAXerife()  # Uncomment to run the main loop


if __name__ == "__main__":
    main()
