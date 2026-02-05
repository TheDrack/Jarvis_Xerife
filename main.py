#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main entry point for Jarvis voice assistant
Integrates JarvisEngine and CommandProcessor to create a voice-activated assistant
"""

from app import JarvisEngine, CommandProcessor


def exemplo_acao(parametro):
    """Exemplo de ação para demonstração"""
    print(f"Ação executada com parâmetro: {parametro}")


def main():
    """
    Main function that initializes and starts the voice assistant
    Waits for 'xerife' activation keyword and processes subsequent commands
    """
    # Initialize engine with 'xerife' as activation keyword
    engine = JarvisEngine(activation_keyword='xerife')
    
    # Initialize command processor
    processor = CommandProcessor()
    
    # Register example commands (can be extended with more commands)
    processor.register_command('teste', exemplo_acao)
    processor.register_command('exemplo', exemplo_acao)
    
    # Start the main loop
    try:
        engine.start(processor)
    except KeyboardInterrupt:
        print("\nEncerrando...")
        engine.stop()


if __name__ == '__main__':
    main()
