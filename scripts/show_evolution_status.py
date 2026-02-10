#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Evolution Status Dashboard

A simple CLI dashboard to visualize JARVIS evolution progress.
Shows overall progress and chapter-by-chapter breakdown.

Usage:
    python scripts/show_evolution_status.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.application.services.capability_manager import CapabilityManager
from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.core.config import settings


def print_progress_bar(percentage: float, width: int = 40):
    """Print a text-based progress bar"""
    filled = int(width * percentage / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {percentage:.1f}%"


def print_chapter_status(chapter_data: dict):
    """Print status for a single chapter"""
    chapter_name = chapter_data['chapter'].replace('_', ' ').title()
    total = chapter_data['total']
    complete = chapter_data['complete']
    partial = chapter_data['partial']
    nonexistent = chapter_data['nonexistent']
    progress = chapter_data['progress_percentage']
    
    # Color codes for terminal (works on most Unix terminals)
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    print(f"\n{BOLD}{BLUE}{chapter_name}{RESET}")
    print(f"  Total Capabilities: {total}")
    print(f"  {GREEN}Complete: {complete}{RESET} | {YELLOW}Partial: {partial}{RESET} | {RED}Not Started: {nonexistent}{RESET}")
    print(f"  Progress: {print_progress_bar(progress)}")


def main():
    """Main dashboard display"""
    print("=" * 70)
    print("          🤖 JARVIS SELF-AWARENESS EVOLUTION DASHBOARD 🤖")
    print("=" * 70)
    
    # Initialize database and capability manager
    db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
    capability_manager = CapabilityManager(engine=db_adapter.engine)
    
    # Get evolution progress
    progress = capability_manager.get_evolution_progress()
    
    # Print overall status
    print(f"\n{'═' * 70}")
    print(f"  OVERALL EVOLUTION STATUS")
    print(f"{'═' * 70}")
    print(f"\n  Total Capabilities: {progress['total_capabilities']}")
    print(f"  ✅ Complete: {progress['complete_capabilities']}")
    print(f"  ⚠️  Partial: {progress['partial_capabilities']}")
    print(f"  ❌ Not Started: {progress['nonexistent_capabilities']}")
    print(f"\n  Overall Progress: {print_progress_bar(progress['overall_progress'], 50)}")
    
    # Print chapter breakdown
    print(f"\n{'═' * 70}")
    print(f"  CHAPTER-BY-CHAPTER BREAKDOWN")
    print(f"{'═' * 70}")
    
    for chapter in progress['chapters']:
        print_chapter_status(chapter)
    
    # Get next evolution step
    print(f"\n{'═' * 70}")
    print(f"  NEXT EVOLUTION STEP")
    print(f"{'═' * 70}")
    
    next_step = capability_manager.get_next_evolution_step()
    if next_step:
        print(f"\n  🎯 Priority Capability: {next_step['capability_name']}")
        print(f"  📖 Chapter: {next_step['chapter'].replace('_', ' ').title()}")
        print(f"  📊 Current Status: {next_step['current_status'].upper()}")
        print(f"  🔢 Priority Score: {next_step['priority_score']} (lower = higher priority)")
        
        blueprint = next_step['blueprint']
        if blueprint.get('libraries'):
            print(f"\n  📚 Required Libraries: {', '.join(blueprint['libraries'])}")
        if blueprint.get('apis'):
            print(f"  🌐 Required APIs: {', '.join(blueprint['apis'])}")
        if blueprint.get('env_vars'):
            print(f"  🔑 Required Env Vars: {', '.join(blueprint['env_vars'])}")
        if blueprint.get('blueprint'):
            print(f"\n  💡 Implementation Blueprint:")
            print(f"     {blueprint['blueprint']}")
    else:
        print("\n  ✨ All capabilities are either complete or have missing resources!")
    
    print(f"\n{'═' * 70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDashboard interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
