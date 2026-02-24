#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JARVIS Evolution RL Status

Shows the Reinforcement Learning evolution status including:
- Efficiency score and improvement
- Success rate
- Commander status message
- Recent actions and rewards

Usage:
    python scripts/show_rl_status.py [--days DAYS]
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.adapters.infrastructure.sqlite_history_adapter import SQLiteHistoryAdapter
from app.adapters.infrastructure.reward_adapter import RewardAdapter
from app.application.services.evolution_loop import EvolutionLoopService
from app.core.config import settings


def print_header():
    """Print the header for the dashboard."""
    print("=" * 70)
    print("          🤖 JARVIS REINFORCEMENT LEARNING STATUS 🤖")
    print("=" * 70)


def print_commander_status(status: dict):
    """Print the commander status message prominently."""
    print("\n" + "=" * 70)
    print("  COMMANDER STATUS")
    print("=" * 70)
    print(f"\n  {status['commander_message']}\n")


def print_metrics(status: dict):
    """Print efficiency metrics."""
    print("=" * 70)
    print("  EFFICIENCY METRICS")
    print("=" * 70)

    efficiency = status['efficiency_score']
    improvement = status['improvement']
    success_rate = status['success_rate']
    total_actions = status['total_actions']
    period = status['period_days']

    # Color codes
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

    # Choose color based on improvement
    if improvement > 0:
        color = GREEN
    elif improvement < 0:
        color = RED
    else:
        color = YELLOW

    print(f"\n  Período analisado: {period} dias")
    print(f"  Total de ações: {total_actions}")
    print(f"  Score de eficiência: {color}{efficiency:+.2f}{RESET} pontos")
    print(f"  Melhoria: {color}{improvement:+.2f}{RESET} pontos ({status['improvement_percentage']:+.1f}%)")
    print(f"  Taxa de sucesso: {GREEN if success_rate >= 70 else YELLOW if success_rate >= 50 else RED}{success_rate:.1f}%{RESET}")
    print()


def print_action_breakdown(stats: dict):
    """Print breakdown by action type."""
    print("=" * 70)
    print("  BREAKDOWN POR TIPO DE AÇÃO")
    print("=" * 70)

    if not stats['by_action_type']:
        print("\n  Nenhuma ação registrada ainda.\n")
        return

    print()
    for action_type, data in sorted(
        stats['by_action_type'].items(),
        key=lambda x: x[1]['total_reward'],
        reverse=True
    ):
        count = data['count']
        total_reward = data['total_reward']
        avg = total_reward / count if count > 0 else 0

        # Choose emoji based on action type
        if 'pass' in action_type or 'success' in action_type or 'complete' in action_type:
            emoji = "✅"
        elif 'fail' in action_type or 'rollback' in action_type:
            emoji = "❌"
        else:
            emoji = "📊"

        print(f"  {emoji} {action_type:20s}: {count:3d} ações, {total_reward:+8.1f} pts (avg: {avg:+6.2f})")
    print()


def print_recent_events(evolution_service: EvolutionLoopService, limit: int = 10):
    """Print recent significant events."""
    print("=" * 70)
    print(f"  ÚLTIMOS {limit} EVENTOS")
    print("=" * 70)

    recent_rewards = evolution_service.reward_provider.get_rewards(limit=limit)

    if not recent_rewards:
        print("\n  Nenhum evento registrado ainda.\n")
        return

    print()
    for reward in recent_rewards:
        action = reward['action_type']
        value = reward['reward_value']
        created = reward['created_at']

        # Choose emoji and color
        if value > 0:
            emoji = "📈"
            color = '\033[92m'  # Green
        else:
            emoji = "📉"
            color = '\033[91m'  # Red

        reset = '\033[0m'

        # Format timestamp
        time_str = created.strftime('%Y-%m-%d %H:%M:%S')

        print(f"  {emoji} {time_str} | {action:20s} | {color}{value:+7.2f}{reset} pts")
    print()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Display JARVIS Reinforcement Learning evolution status'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to analyze (default: 7)'
    )

    args = parser.parse_args()

    try:
        # Initialize adapters and services
        db_adapter = SQLiteHistoryAdapter(database_url=settings.database_url)
        reward_adapter = RewardAdapter(engine=db_adapter.engine)
        evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

        # Get evolution status
        status = evolution_service.get_evolution_status(days=args.days)

        # Print dashboard
        print_header()
        print_commander_status(status)
        print_metrics(status)
        print_action_breakdown(status['statistics'])
        print_recent_events(evolution_service, limit=10)

        print("=" * 70)
        print()

    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
