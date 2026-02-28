#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example: LLM-based Capability Detection

This example demonstrates how to use the new LLM-based capability detection
system to analyze the codebase and identify implemented capabilities.
"""

import asyncio
import os
from pathlib import Path
from app.adapters.infrastructure.ai_gateway import AIGateway
from app.application.services.llm_capability_detector import LLMCapabilityDetector


async def main():
    """Demonstrate LLM-based capability detection"""
    
    print("=" * 70)
    print("  LLM-Based Capability Detection Demo")
    print("=" * 70)
    print()
    
    # Initialize AI Gateway
    print("Initializing AI Gateway...")
    groq_api_key = os.getenv("GROQ_API_KEY")
    gemini_api_key = os.getenv("GOOGLE_API_KEY")
    
    if not groq_api_key and not gemini_api_key:
        print("⚠️  Warning: No API keys found. Set GROQ_API_KEY or GOOGLE_API_KEY")
        print("   Capability detection requires LLM access.")
        return
    
    ai_gateway = AIGateway(
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
    )
    print("✓ AI Gateway initialized")
    print()
    
    # Create capability detector
    detector = LLMCapabilityDetector(
        ai_gateway=ai_gateway,
        repository_root=Path.cwd()
    )
    
    # Test capabilities to detect
    test_capabilities = [
        {
            "id": 1,
            "name": "Voice Command Processing",
            "description": "Ability to process voice commands and convert to actions"
        },
        {
            "id": 2,
            "name": "AI-Powered Intent Recognition",
            "description": "Using LLM to understand user intent from natural language"
        },
        {
            "id": 3,
            "name": "Self-Healing Code Repair",
            "description": "Automatically detect and fix code errors using GitHub Actions"
        },
        {
            "id": 4,
            "name": "Multi-Device Orchestration",
            "description": "Coordinate tasks across multiple devices based on capabilities"
        },
    ]
    
    print("Analyzing capabilities...")
    print("-" * 70)
    
    for capability in test_capabilities:
        print(f"\nCapability: {capability['name']}")
        print(f"Description: {capability['description']}")
        print(f"Analyzing...")
        
        result = await detector.detect_capability_async(
            capability_id=capability['id'],
            capability_name=capability['name'],
            capability_description=capability['description']
        )
        
        print(f"\n  Status: {result['status'].upper()}")
        print(f"  Confidence: {result['confidence']:.2f}")
        
        if result['evidence']:
            print(f"  Evidence:")
            for evidence in result['evidence'][:3]:  # Show first 3
                print(f"    • {evidence}")
        
        if result['files_found']:
            print(f"  Files found:")
            for file in result['files_found'][:3]:  # Show first 3
                print(f"    • {file}")
        
        if result['recommendations']:
            print(f"  Recommendations:")
            for rec in result['recommendations'][:2]:  # Show first 2
                print(f"    • {rec}")
        
        print()
    
    print("=" * 70)
    print("Demo complete!")
    print()
    
    print("Benefits of LLM-based capability detection:")
    print("  ✓ Understands code semantics, not just keywords")
    print("  ✓ Distinguishes between partial and complete implementations")
    print("  ✓ Provides actionable recommendations")
    print("  ✓ Higher accuracy than keyword-based scanning")
    print("  ✓ Confidence scores for each detection")
    print()


if __name__ == "__main__":
    asyncio.run(main())
