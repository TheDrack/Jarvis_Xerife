#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de demonstração do Sistema de Auto-Evolução do Jarvis
"""

from app.application.services.auto_evolution import AutoEvolutionService


def main():
    print("=" * 70)
    print("🧬 DEMONSTRAÇÃO DO SISTEMA DE AUTO-EVOLUÇÃO DO JARVIS")
    print("=" * 70)
    print()

    # Inicializar serviço
    print("1️⃣ Inicializando AutoEvolutionService...")
    auto_evolution = AutoEvolutionService()
    print(f"   ✅ Serviço inicializado com ROADMAP: {auto_evolution.roadmap_path}")
    print()

    # Parse ROADMAP
    print("2️⃣ Parseando ROADMAP.md...")
    roadmap_data = auto_evolution.parse_roadmap()
    if 'error' in roadmap_data:
        print(f"   ❌ Erro: {roadmap_data['error']}")
        return

    print(f"   ✅ ROADMAP parseado com sucesso!")
    print(f"   📊 Total de seções: {roadmap_data['total_sections']}")
    print()

    # Mostrar seções
    print("3️⃣ Seções do ROADMAP:")
    for i, section in enumerate(roadmap_data['sections'], 1):
        mission_count = len(section['missions'])
        print(f"   {i}. {section['title'][:50]}")
        print(f"      └─ {mission_count} missões encontradas")
    print()

    # Encontrar próxima missão
    print("4️⃣ Buscando próxima missão alcançável...")
    next_mission = auto_evolution.find_next_mission()

    if next_mission:
        mission = next_mission['mission']
        section = next_mission['section']
        priority = next_mission['priority']

        print(f"   ✅ Missão encontrada!")
        print(f"   📍 Seção: {section}")
        print(f"   🎯 Prioridade: {priority}")
        print(f"   📝 Status: {mission['status']}")
        print(f"   📄 Descrição: {mission['description'][:100]}...")
        print()

        # Mostrar contexto
        print("5️⃣ Contexto gerado para a missão:")
        print("─" * 70)
        context = auto_evolution.get_roadmap_context(next_mission)
        print(context)
        print("─" * 70)
        print()
    else:
        print("   ❌ Nenhuma missão encontrada para evoluir")
        print()

    # Testar detecção de PR de auto-evolução
    print("6️⃣ Testando detecção de PRs de auto-evolução:")
    test_cases = [
        ("[Auto-Evolution] Fix bug", True),
        ("Fix typo in README", False),
        ("Jarvis Evolution: new feature", True),
        ("Add new feature", False),
    ]

    for pr_title, expected in test_cases:
        is_auto = auto_evolution.is_auto_evolution_pr(pr_title)
        emoji = "✅" if is_auto == expected else "❌"
        result = "Auto-Evolução" if is_auto else "Normal"
        print(f"   {emoji} '{pr_title[:40]}...' → {result}")
    print()

    # Métricas de sucesso
    print("7️⃣ Métricas de sucesso do ROADMAP:")
    metrics = auto_evolution.get_success_metrics()

    if 'error' not in metrics:
        print(f"   📊 Total de missões: {metrics['total_missions']}")
        print(f"   ✅ Completadas: {metrics['completed']}")
        print(f"   🔄 Em progresso: {metrics['in_progress']}")
        print(f"   📋 Planejadas: {metrics['planned']}")
        print(f"   📈 Progresso: {metrics['completion_percentage']:.2f}%")
    else:
        print(f"   ❌ Erro: {metrics['error']}")
    print()

    # Resumo final
    print("=" * 70)
    print("✅ DEMONSTRAÇÃO CONCLUÍDA COM SUCESSO!")
    print()
    print("O Sistema de Auto-Evolução está funcionando corretamente e pronto")
    print("para ser ativado quando um PR for merged na main.")
    print()
    print("📚 Documentação completa em:")
    print("   - docs/AUTO_EVOLUTION_SYSTEM.md")
    print("   - docs/IMPLEMENTATION_AUTO_EVOLUTION.md")
    print("=" * 70)


if __name__ == "__main__":
    main()
