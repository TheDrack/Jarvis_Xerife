#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demo: Jarvis Gears System

This script demonstrates the Gears System (Sistema de Marchas) in action,
showing how Jarvis automatically switches between different AI models
based on availability and performance.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider, GroqGear

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_basic_usage():
    """Demonstrate basic usage of the Gears System"""
    print("\n" + "=" * 80)
    print("DEMO 1: Basic Gears System Usage")
    print("=" * 80 + "\n")
    
    # Initialize gateway
    gateway = AIGateway(
        groq_api_key=os.getenv("GROQ_API_KEY", "demo_key"),
        gemini_api_key=os.getenv("GOOGLE_API_KEY", "demo_key"),
    )
    
    print(f"✅ Gateway initialized with:")
    print(f"   - High Gear: {gateway.groq_high_gear_model}")
    print(f"   - Low Gear: {gateway.groq_low_gear_model}")
    print(f"   - Cannon Shot: {gateway.gemini_model}")
    print(f"   - Current Gear: {gateway.current_groq_gear.value}")
    print(f"   - Auto-repair: {gateway.enable_auto_repair}")
    
    # Show current model
    print(f"\n🏎️ Current model in use: {gateway.groq_model}")


async def demo_gear_shifting():
    """Demonstrate automatic gear shifting"""
    print("\n" + "=" * 80)
    print("DEMO 2: Automatic Gear Shifting")
    print("=" * 80 + "\n")
    
    gateway = AIGateway(
        groq_api_key=os.getenv("GROQ_API_KEY", "demo_key"),
        gemini_api_key=os.getenv("GOOGLE_API_KEY", "demo_key"),
    )
    
    # Show High Gear
    print(f"🏎️ Starting in High Gear: {gateway.groq_model}")
    assert gateway.current_groq_gear == GroqGear.HIGH_GEAR
    
    # Shift to Low Gear
    print("\n⚠️ Simulating rate limit - shifting to Low Gear...")
    gateway._shift_to_low_gear()
    print(f"⚙️ Now in Low Gear: {gateway.groq_model}")
    assert gateway.current_groq_gear == GroqGear.LOW_GEAR
    
    # Shift back to High Gear
    print("\n✅ Rate limit recovered - shifting back to High Gear...")
    gateway._shift_to_high_gear()
    print(f"🏎️ Back in High Gear: {gateway.groq_model}")
    assert gateway.current_groq_gear == GroqGear.HIGH_GEAR


async def demo_provider_selection():
    """Demonstrate provider selection logic"""
    print("\n" + "=" * 80)
    print("DEMO 3: Intelligent Provider Selection")
    print("=" * 80 + "\n")
    
    gateway = AIGateway(
        groq_api_key=os.getenv("GROQ_API_KEY", "demo_key"),
        gemini_api_key=os.getenv("GOOGLE_API_KEY", "demo_key"),
    )
    
    # Mock clients to be available
    from unittest.mock import Mock
    gateway.groq_client = Mock()
    gateway.gemini_client = Mock()
    
    # Test 1: Short payload -> Groq
    print("📊 Test 1: Short payload (< 10k tokens)")
    short_payload = "Hello, how are you?"
    provider = gateway.select_provider(short_payload)
    print(f"   ✅ Selected: {provider.value} (expected: groq)")
    
    # Test 2: Large payload -> Gemini
    print("\n📊 Test 2: Large payload (> 10k tokens)")
    large_payload = "word " * 15000  # Approx 15k tokens
    provider = gateway.select_provider(large_payload)
    print(f"   ✅ Selected: {provider.value} (expected: gemini)")
    
    # Test 3: Multimodal -> Gemini
    print("\n📊 Test 3: Multimodal request")
    provider = gateway.select_provider("Any text", multimodal=True)
    print(f"   ✅ Selected: {provider.value} (expected: gemini)")
    
    # Test 4: Force provider
    print("\n📊 Test 4: Force specific provider")
    provider = gateway.select_provider("Short text", force_provider=LLMProvider.GEMINI)
    print(f"   ✅ Selected: {provider.value} (expected: gemini)")


async def demo_backward_compatibility():
    """Demonstrate backward compatibility"""
    print("\n" + "=" * 80)
    print("DEMO 4: Backward Compatibility")
    print("=" * 80 + "\n")
    
    # Old way (still works)
    print("📦 Old initialization method (still supported):")
    gateway_old = AIGateway(
        groq_api_key="demo_key",
        gemini_api_key="demo_key",
        groq_model="llama-3.3-70b-versatile"  # Old parameter
    )
    print(f"   ✅ gateway.groq_model = {gateway_old.groq_model}")
    
    # New way (recommended)
    print("\n📦 New initialization method (recommended):")
    gateway_new = AIGateway(
        groq_api_key="demo_key",
        gemini_api_key="demo_key",
        groq_high_gear_model="llama-3.3-70b-versatile",
        groq_low_gear_model="llama-3.1-8b-instant"
    )
    print(f"   ✅ gateway.groq_high_gear_model = {gateway_new.groq_high_gear_model}")
    print(f"   ✅ gateway.groq_low_gear_model = {gateway_new.groq_low_gear_model}")
    print(f"   ✅ gateway.groq_model = {gateway_new.groq_model} (property)")


async def demo_environment_variables():
    """Demonstrate environment variable configuration"""
    print("\n" + "=" * 80)
    print("DEMO 5: Environment Variable Configuration")
    print("=" * 80 + "\n")
    
    print("📝 Supported environment variables:")
    print("   - GROQ_API_KEY: Groq API key")
    print("   - GROQ_MODEL or GROQ_HIGH_GEAR_MODEL: High Gear model")
    print("   - GROQ_LOW_GEAR_MODEL: Low Gear model")
    print("   - GOOGLE_API_KEY or GEMINI_API_KEY: Gemini API key")
    print("   - GEMINI_MODEL: Gemini model")
    
    print("\n📋 Example .env configuration:")
    print("""
    GROQ_API_KEY=your_groq_api_key
    GROQ_MODEL=llama-3.3-70b-versatile
    GROQ_LOW_GEAR_MODEL=llama-3.1-8b-instant
    
    GOOGLE_API_KEY=your_google_api_key
    GEMINI_MODEL=gemini-1.5-pro
    """)


async def main():
    """Run all demos"""
    print("\n🚀 Jarvis Gears System Demo")
    print("=" * 80)
    
    try:
        await demo_basic_usage()
        await demo_gear_shifting()
        await demo_provider_selection()
        await demo_backward_compatibility()
        await demo_environment_variables()
        
        print("\n" + "=" * 80)
        print("✅ All demos completed successfully!")
        print("=" * 80)
        
        print("\n📚 For more information, see:")
        print("   - docs/GEARS_SYSTEM.md")
        print("   - app/adapters/infrastructure/ai_gateway.py")
        print("   - tests/adapters/test_ai_gateway_gears.py")
        
    except Exception as e:
        print(f"\n❌ Error running demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
