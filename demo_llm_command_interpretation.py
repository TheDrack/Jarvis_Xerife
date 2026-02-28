#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example: LLM-based Command Interpretation

This example demonstrates how to use the new LLM-based command interpretation
system instead of traditional keyword matching.
"""

import asyncio
import os
from app.adapters.infrastructure.ai_gateway import AIGateway
from app.core.llm_config import create_command_interpreter, LLMConfig


async def main():
    """Demonstrate LLM-based command interpretation"""
    
    print("=" * 70)
    print("  LLM-Based Command Interpretation Demo")
    print("=" * 70)
    print()
    
    # Check configuration
    print("Current Configuration:")
    config = LLMConfig.get_config_summary()
    for key, value in config.items():
        print(f"  {key}: {value}")
    print()
    
    # Initialize AI Gateway
    print("Initializing AI Gateway...")
    groq_api_key = os.getenv("GROQ_API_KEY")
    gemini_api_key = os.getenv("GOOGLE_API_KEY")
    
    if not groq_api_key and not gemini_api_key:
        print("⚠️  Warning: No API keys found. Set GROQ_API_KEY or GOOGLE_API_KEY")
        print("   For this demo, we'll use the fallback keyword-based interpreter")
        ai_gateway = None
    else:
        ai_gateway = AIGateway(
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
        )
        print("✓ AI Gateway initialized")
    print()
    
    # Create command interpreter
    interpreter = create_command_interpreter(wake_word="jarvis", ai_gateway=ai_gateway)
    
    print(f"Interpreter: {type(interpreter).__name__}")
    print()
    
    # Test commands
    test_commands = [
        "jarvis escreva hello world",
        "jarvis digite meu nome",
        "jarvis aperte enter",
        "jarvis abra o google",
        "jarvis internet",
        "jarvis procurar por login na página",
    ]
    
    print("Testing commands:")
    print("-" * 70)
    
    for command in test_commands:
        print(f"\nCommand: '{command}'")
        
        if ai_gateway:
            # Use LLM-based interpretation (async)
            intent = await interpreter.interpret_async(command)
        else:
            # Use keyword-based interpretation (sync)
            intent = interpreter.interpret(command)
        
        print(f"  Type: {intent.command_type}")
        print(f"  Parameters: {intent.parameters}")
        print(f"  Confidence: {intent.confidence:.2f}")
    
    print()
    print("=" * 70)
    print("Demo complete!")
    print()
    
    # Show advantages of LLM-based system
    print("Advantages of LLM-based system:")
    print("  ✓ Understands natural language variations")
    print("  ✓ Higher accuracy in intent classification")
    print("  ✓ Automatic fallback to keywords on errors")
    print("  ✓ No need to update keyword lists manually")
    print("  ✓ Provides confidence scores")
    print()


if __name__ == "__main__":
    asyncio.run(main())
