#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example: GitHub Copilot Context Provider

This example demonstrates how to generate repository context for GitHub Agents
using LLM-based analysis.
"""

import asyncio
import json
import os
from pathlib import Path
from app.adapters.infrastructure.ai_gateway import AIGateway
from app.adapters.infrastructure.copilot_context_provider import GitHubCopilotContextProvider


async def main():
    """Demonstrate GitHub Copilot context generation"""
    
    print("=" * 70)
    print("  GitHub Copilot Context Provider Demo")
    print("=" * 70)
    print()
    
    # Initialize AI Gateway
    print("Initializing AI Gateway...")
    groq_api_key = os.getenv("GROQ_API_KEY")
    gemini_api_key = os.getenv("GOOGLE_API_KEY")
    
    if not groq_api_key and not gemini_api_key:
        print("⚠️  Warning: No API keys found. Set GROQ_API_KEY or GOOGLE_API_KEY")
        print("   Context generation requires LLM access.")
        print()
        print("Showing fallback context...")
        ai_gateway = None
    else:
        ai_gateway = AIGateway(
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
        )
        print("✓ AI Gateway initialized")
    print()
    
    # Create context provider
    provider = GitHubCopilotContextProvider(
        ai_gateway=ai_gateway,
        repository_root=Path.cwd()
    )
    
    # Generate general repository context
    print("Generating repository context...")
    print("-" * 70)
    
    context = await provider.generate_repository_context()
    
    print("\n📋 Repository Analysis:")
    print(f"  Architecture: {context.get('architecture', 'Unknown')}")
    
    if context.get('key_patterns'):
        print(f"\n  Key Patterns:")
        for pattern in context['key_patterns'][:3]:
            print(f"    • {pattern}")
    
    if context.get('folder_purposes'):
        print(f"\n  Folder Organization:")
        for folder, purpose in list(context['folder_purposes'].items())[:3]:
            print(f"    • {folder}: {purpose}")
    
    if context.get('integration_points'):
        print(f"\n  Integration Points:")
        for point in context['integration_points'][:3]:
            print(f"    • {point}")
    
    if context.get('best_practices'):
        print(f"\n  Best Practices:")
        for practice in context['best_practices'][:3]:
            print(f"    • {practice}")
    
    print()
    
    # Generate issue-specific context
    print("\nGenerating context for a specific issue...")
    print("-" * 70)
    
    issue_description = """
    Add a feature to allow users to upload profile photos.
    The photos should be stored in S3 and thumbnails should be generated.
    """
    
    print(f"Issue: {issue_description.strip()}")
    print()
    
    issue_context = await provider.generate_context_for_issue(issue_description)
    
    print("📌 Issue-Specific Guidance:")
    
    if issue_context.get('affected_areas'):
        print(f"\n  Affected Areas:")
        for area in issue_context['affected_areas']:
            print(f"    • {area}")
    
    if issue_context.get('files_to_modify'):
        print(f"\n  Files to Modify:")
        for file in issue_context['files_to_modify']:
            print(f"    • {file}")
    
    if issue_context.get('files_to_create'):
        print(f"\n  Files to Create:")
        for file in issue_context['files_to_create']:
            print(f"    • {file}")
    
    if issue_context.get('implementation_notes'):
        print(f"\n  Implementation Notes:")
        for note in issue_context['implementation_notes'][:3]:
            print(f"    • {note}")
    
    if issue_context.get('potential_risks'):
        print(f"\n  Potential Risks:")
        for risk in issue_context['potential_risks'][:3]:
            print(f"    • {risk}")
    
    print()
    
    # Save context for GitHub Agents
    print("\nSaving context for GitHub Agents...")
    output_file = Path("/tmp/repository_context.json")
    saved_path = provider.save_context_for_github_agents(context, output_file)
    print(f"✓ Context saved to: {saved_path}")
    
    # Show a snippet of the saved context
    print(f"\nContext file preview (first 500 chars):")
    with open(saved_path, 'r') as f:
        preview = f.read(500)
        print(preview)
        if len(preview) >= 500:
            print("...")
    
    print()
    print("=" * 70)
    print("Demo complete!")
    print()
    
    print("How GitHub Agents use this context:")
    print("  1. Read .github/repository_context.json")
    print("  2. Understand the architecture and patterns")
    print("  3. Make context-aware code changes")
    print("  4. Follow best practices automatically")
    print("  5. Identify integration points correctly")
    print()


if __name__ == "__main__":
    asyncio.run(main())
