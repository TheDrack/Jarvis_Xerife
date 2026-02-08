#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo script for Xerife Strategist Module

This script demonstrates the autonomous improvement proposal system with ROI analysis.
"""

import json
from pathlib import Path

from app.application.services.strategist_service import StrategistService, BudgetExceededException
from app.domain.models.viability import (
    CostEstimate,
    ImpactEstimate,
    ImpactLevel,
    RiskEstimate,
    RiskLevel,
)


def print_header(title: str):
    """Print a formatted header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def demo_viability_analysis():
    """Demonstrate viability matrix creation and ROI calculation"""
    print_header("1. Análise de Viabilidade (Viability Matrix)")
    
    # Create a good proposal
    cost = CostEstimate(
        api_tokens=5000,
        api_cost_usd=0.10,
        code_complexity="moderate",
        lines_of_code_estimate=200,
        development_time_hours=3.0,
        ci_cd_time_minutes=15,
    )
    
    impact = ImpactEstimate(
        performance_gain_percent=35.0,
        error_reduction_percent=25.0,
        potential_bugs_prevented=5,
        user_utility_level=ImpactLevel.HIGH,
        technical_debt_reduction=True,
        code_maintainability_improvement=True,
    )
    
    risk = RiskEstimate(
        risk_level=RiskLevel.MEDIUM,
        introduces_new_dependencies=True,
        risk_description="Pode afetar módulos de cache existentes",
        mitigation_strategy="Adicionar testes de regressão e feature flag",
    )
    
    strategist = StrategistService(
        default_budget_cap=10.0,
        min_roi_threshold=0.5,
    )
    
    matrix = strategist.generate_viability_matrix(
        proposal_title="Implementar Redis Cache para Sessões",
        proposal_description="Substituir cache em memória por Redis distribuído para melhorar escalabilidade",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    # Display analysis
    print("📊 Proposta:", matrix.proposal_title)
    print("📝 Descrição:", matrix.proposal_description)
    print()
    print("💰 Análise de Custos:")
    print(f"  • Tokens de API: {cost.api_tokens}")
    print(f"  • Custo estimado: ${cost.api_cost_usd:.2f} USD")
    print(f"  • Complexidade: {cost.code_complexity}")
    print(f"  • Tempo de dev: {cost.development_time_hours}h")
    print(f"  • Score de Custo: {cost.total_cost_score():.1f}/10")
    print()
    print("🎯 Análise de Impacto:")
    print(f"  • Ganho de performance: {impact.performance_gain_percent}%")
    print(f"  • Redução de erros: {impact.error_reduction_percent}%")
    print(f"  • Bugs prevenidos: {impact.potential_bugs_prevented}")
    print(f"  • Utilidade: {impact.user_utility_level.value}")
    print(f"  • Score de Impacto: {impact.total_impact_score():.1f}/10")
    print()
    print("⚠️  Análise de Riscos:")
    print(f"  • Nível: {risk.risk_level.value}")
    print(f"  • Descrição: {risk.risk_description}")
    print(f"  • Mitigação: {risk.mitigation_strategy}")
    print(f"  • Score de Risco: {risk.total_risk_score():.1f}/10")
    print()
    print(f"📈 ROI Score: {matrix.calculate_roi():.2f}")
    print(f"✅ Viável: {matrix.is_viable()}")
    
    return matrix, strategist


def demo_rfc_generation(matrix, strategist):
    """Demonstrate RFC generation for approved proposals"""
    print_header("2. Geração de RFC (Request for Comments)")
    
    if matrix.is_viable():
        print("✅ Proposta aprovada! Gerando RFC...")
        
        # Archive proposal
        archive_path = strategist.archive_proposal(matrix)
        print(f"📁 Proposta arquivada: {archive_path}")
        
        # Generate RFC
        rfc_path = strategist.generate_rfc(matrix)
        print(f"📄 RFC gerado: {rfc_path}")
        
        # Display RFC preview
        print("\n--- Preview do RFC ---")
        with open(rfc_path, 'r') as f:
            lines = f.readlines()[:30]  # First 30 lines
            print(''.join(lines))
        print("... (truncado)")
    else:
        print(f"❌ Proposta rejeitada: {matrix.rejection_reason}")
        archive_path = strategist.archive_proposal(matrix)
        print(f"📁 Proposta arquivada como rejeitada: {archive_path}")


def demo_decision_interface(matrix, strategist):
    """Demonstrate the decision interface for commander approval"""
    print_header("3. Interface de Decisão para o Comandante")
    
    prompt = strategist.format_decision_prompt(matrix)
    print(prompt)


def demo_budget_tracking():
    """Demonstrate budget cap and cost tracking"""
    print_header("4. Rastreamento de Orçamento (Budget Cap)")
    
    strategist = StrategistService(default_budget_cap=5.0)
    
    print("💰 Orçamento configurado: $5.00 USD")
    print()
    
    # Simulate token usage checks
    test_cases = [
        (1000, 0.002, "Pequena tarefa (1K tokens)"),
        (5000, 0.002, "Tarefa média (5K tokens)"),
        (10000, 0.002, "Tarefa grande (10K tokens)"),
        (1000000, 0.002, "Tarefa muito grande (1M tokens) - deve exceder"),
    ]
    
    for tokens, cost_per_1k, description in test_cases:
        print(f"📊 {description}")
        try:
            cost, within = strategist.check_budget(
                used_tokens=tokens,
                token_cost_per_1k=cost_per_1k,
            )
            print(f"   Custo: ${cost:.4f} - {'✅ Dentro do orçamento' if within else '❌ Excedeu'}")
        except BudgetExceededException as e:
            print(f"   ❌ ORÇAMENTO EXCEDIDO: ${e.used:.2f} > ${e.limit:.2f}")
        print()


def demo_error_log_analysis():
    """Demonstrate error log analysis for refactoring suggestions"""
    print_header("5. Análise de Logs e Sugestões de Refatoração")
    
    strategist = StrategistService()
    
    # Simulate error logs from the system
    error_logs = [
        {
            "error_message": "NoneType object has no attribute 'user_id'",
            "error_type": "AttributeError",
            "count": 12,
            "timestamp": "2024-01-15",
        },
        {
            "error_message": "Connection timeout to database",
            "error_type": "TimeoutError",
            "count": 8,
            "timestamp": "2024-01-15",
        },
        {
            "error_message": "Division by zero in metrics calculation",
            "error_type": "ZeroDivisionError",
            "count": 5,
            "timestamp": "2024-01-16",
        },
        {
            "error_message": "Invalid API key",
            "error_type": "AuthenticationError",
            "count": 2,
            "timestamp": "2024-01-16",
        },
    ]
    
    print("📋 Logs de erro encontrados:")
    for log in error_logs:
        print(f"  • {log['error_type']}: {log['error_message'][:50]}... (count: {log['count']})")
    
    print("\n💡 Sugestões de refatoração (threshold: count >= 3):")
    suggestions = strategist.analyze_error_logs(error_logs)
    
    for i, suggestion in enumerate(suggestions, 1):
        print(f"\n{i}. {suggestion}")


def demo_rejected_proposal():
    """Demonstrate a proposal that gets rejected"""
    print_header("6. Exemplo de Proposta Rejeitada")
    
    # Create a risky proposal
    cost = CostEstimate(
        api_tokens=50000,
        api_cost_usd=5.0,
        code_complexity="complex",
        lines_of_code_estimate=1000,
        development_time_hours=20.0,
        ci_cd_time_minutes=60,
    )
    
    impact = ImpactEstimate(
        performance_gain_percent=5.0,  # Low impact
        user_utility_level=ImpactLevel.LOW,
    )
    
    risk = RiskEstimate(
        risk_level=RiskLevel.CRITICAL,  # Critical risk
        breaks_legacy_systems=True,
        security_concerns=True,
        risk_description="Requer reescrita completa do sistema de autenticação",
    )
    
    strategist = StrategistService()
    
    matrix = strategist.generate_viability_matrix(
        proposal_title="Reescrever Sistema de Autenticação",
        proposal_description="Reescrever completamente o módulo de autenticação",
        cost=cost,
        impact=impact,
        risk=risk,
    )
    
    print(f"📊 Proposta: {matrix.proposal_title}")
    print(f"💰 Custo Score: {cost.total_cost_score():.1f}/10")
    print(f"🎯 Impacto Score: {impact.total_impact_score():.1f}/10")
    print(f"⚠️  Risco Score: {risk.total_risk_score():.1f}/10")
    print(f"📈 ROI: {matrix.calculate_roi():.2f}")
    print()
    print(f"❌ Resultado: REJEITADA")
    print(f"📝 Razão: {matrix.rejection_reason}")
    
    # Archive it
    archive_path = strategist.archive_proposal(matrix)
    print(f"📁 Arquivada em: {archive_path}")


def demo_task_runner_budget():
    """Demonstrate TaskRunner with budget tracking"""
    print_header("7. TaskRunner com Controle de Orçamento")
    
    from app.application.services.task_runner import TaskRunner
    import tempfile
    
    cache_dir = Path(tempfile.mkdtemp(prefix="demo_xerife_"))
    
    runner = TaskRunner(
        cache_dir=cache_dir,
        use_venv=False,
        sandbox_mode=True,
        budget_cap_usd=10.0,
    )
    
    print(f"🔒 Sandbox Mode: {runner.sandbox_mode}")
    print(f"💰 Budget Cap: ${runner.budget_cap_usd:.2f}")
    print()
    
    # Track some mission costs
    missions = [
        ("mission_001", 2.50, "Análise de sentimento"),
        ("mission_002", 3.75, "Geração de código"),
        ("mission_003", 1.25, "Tradução de texto"),
    ]
    
    for mission_id, cost, description in missions:
        runner.track_mission_cost(mission_id, cost)
        print(f"✅ {mission_id}: ${cost:.2f} - {description}")
    
    print()
    status = runner.get_budget_status()
    print("📊 Status do Orçamento:")
    print(f"  • Total gasto: ${status['total_cost_usd']:.2f}")
    print(f"  • Limite: ${status['budget_cap_usd']:.2f}")
    print(f"  • Restante: ${status['remaining_usd']:.2f}")
    print(f"  • Status: {'✅ OK' if status['within_budget'] else '❌ EXCEDIDO'}")
    print(f"  • Missões rastreadas: {status['missions_tracked']}")


def main():
    """Run all demos"""
    print_header("🎯 Xerife Strategist - Sistema de Propostas Autônomas com ROI")
    
    print("""
Este demo demonstra o módulo Xerife Strategist, que permite ao Jarvis propor
melhorias de forma autônoma, mas sob rigoroso controle de custo-benefício.

Características principais:
1. Análise de Viabilidade com ROI (Return on Investment)
2. Geração automática de RFCs (Request for Comments)
3. Interface de decisão para aprovação do comandante
4. Controle de orçamento (Budget Cap) por missão
5. Modo Sandbox para execução segura
6. Análise de logs para refatoração preventiva
    """)
    
    input("\nPressione ENTER para continuar...")
    
    # Demo 1: Viability Analysis
    matrix, strategist = demo_viability_analysis()
    input("\nPressione ENTER para continuar...")
    
    # Demo 2: RFC Generation
    demo_rfc_generation(matrix, strategist)
    input("\nPressione ENTER para continuar...")
    
    # Demo 3: Decision Interface
    demo_decision_interface(matrix, strategist)
    input("\nPressione ENTER para continuar...")
    
    # Demo 4: Budget Tracking
    demo_budget_tracking()
    input("\nPressione ENTER para continuar...")
    
    # Demo 5: Error Log Analysis
    demo_error_log_analysis()
    input("\nPressione ENTER para continuar...")
    
    # Demo 6: Rejected Proposal
    demo_rejected_proposal()
    input("\nPressione ENTER para continuar...")
    
    # Demo 7: TaskRunner Budget
    demo_task_runner_budget()
    
    print_header("✅ Demo Concluído!")
    print("""
Próximos passos:
1. Revisar as propostas arquivadas em docs/proposals/
2. Revisar o RFC gerado
3. Integrar o Strategist com o sistema de ThoughtLog
4. Adicionar automação de Git para criação de branches
5. Implementar dashboard de visualização

Para mais informações, consulte: docs/XERIFE_STRATEGIST.md
    """)


if __name__ == "__main__":
    main()
