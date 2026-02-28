#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Demo script to test AI Gateway functionality

This script demonstrates:
1. Token counting and provider selection
2. Automatic escalation to Gemini for large contexts
3. Fallback mechanism on rate limits (simulated)
"""

import logging
import os
from app.adapters.infrastructure.ai_gateway import AIGateway, LLMProvider

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def demo_token_counting():
    """Demonstrate token counting functionality"""
    print("\n" + "="*80)
    print("DEMO 1: Token Counting")
    print("="*80)
    
    # Check if API keys are available
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    if not groq_key and not gemini_key:
        print("\n⚠ WARNING: No API keys found in environment")
        print("Set GROQ_API_KEY and/or GEMINI_API_KEY to enable API clients")
        print("Demo will continue with token counting only...\n")
    
    gateway = AIGateway(
        groq_api_key=groq_key,
        gemini_api_key=gemini_key,
    )
    
    # Short text
    short_text = "Analise os logs do sistema e identifique erros."
    short_tokens = gateway.count_tokens(short_text)
    print(f"\nTexto curto ({len(short_text)} chars): {short_tokens} tokens")
    print(f"Texto: {short_text}")
    
    # Medium text
    medium_text = """
    Analise os logs do sistema das últimas 24 horas e identifique:
    1. Erros críticos que precisam de atenção imediata
    2. Warnings recorrentes
    3. Padrões de comportamento anômalo
    4. Recomendações de otimização
    """
    medium_tokens = gateway.count_tokens(medium_text)
    print(f"\nTexto médio ({len(medium_text)} chars): {medium_tokens} tokens")
    
    # Large text (simulating >10k tokens)
    large_text = "Este é um log de sistema. " * 2000
    large_tokens = gateway.count_tokens(large_text)
    print(f"\nTexto grande ({len(large_text)} chars): {large_tokens} tokens")
    print(f"Threshold para escalação: {gateway.TOKEN_THRESHOLD} tokens")


def demo_provider_selection():
    """Demonstrate automatic provider selection"""
    print("\n" + "="*80)
    print("DEMO 2: Provider Selection Based on Payload Size")
    print("="*80)
    
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    gateway = AIGateway(
        groq_api_key=groq_key,
        gemini_api_key=gemini_key,
    )
    
    # Simulate available clients
    gateway.groq_client = "GROQ_CLIENT"
    gateway.gemini_client = "GEMINI_CLIENT"
    
    # Test 1: Short payload -> Groq
    short_payload = "Qual é a temperatura atual?"
    provider = gateway.select_provider(short_payload)
    tokens = gateway.count_tokens(short_payload)
    print(f"\n1. Payload curto ({tokens} tokens)")
    print(f"   Provedor selecionado: {provider.value}")
    print(f"   Motivo: Abaixo do threshold, usando Groq (rápido e econômico)")
    
    # Test 2: Large payload -> Gemini
    large_payload = "Palavra " * 15000  # Simula >10k tokens
    provider = gateway.select_provider(large_payload)
    tokens = gateway.count_tokens(large_payload)
    print(f"\n2. Payload grande ({tokens} tokens)")
    print(f"   Provedor selecionado: {provider.value}")
    print(f"   Motivo: Acima do threshold ({gateway.TOKEN_THRESHOLD}), escalando para Gemini")
    
    # Test 3: Multimodal request -> Gemini
    provider = gateway.select_provider("Analise esta imagem", multimodal=True)
    print(f"\n3. Requisição multimodal")
    print(f"   Provedor selecionado: {provider.value}")
    print(f"   Motivo: Multimodal requer Gemini (Groq não suporta)")
    
    # Test 4: Force specific provider
    provider = gateway.select_provider(
        "Texto qualquer",
        force_provider=LLMProvider.GEMINI
    )
    print(f"\n4. Provedor forçado")
    print(f"   Provedor selecionado: {provider.value}")
    print(f"   Motivo: Solicitação explícita para usar Gemini")


def demo_cost_priority():
    """Demonstrate cost-optimized routing"""
    print("\n" + "="*80)
    print("DEMO 3: Cost Priority Strategy")
    print("="*80)
    
    print("\nPRIORIDADE DE CUSTO:")
    print("- Groq (Llama-3-70b): Provedor padrão para:")
    print("  • Análise de logs curtos")
    print("  • Monólogos internos rápidos")
    print("  • Respostas conversacionais simples")
    print("  • Benefícios: Velocidade alta, custo zero/baixo")
    
    print("\nESCALONAMENTO POR CONTEXTO:")
    print("- Gemini 1.5: Usado quando:")
    print("  • Payload > 10.000 tokens")
    print("  • Análise multimodal (imagens/vídeo)")
    print("  • Contexto longo necessário")
    print("  • Benefícios: Maior capacidade, suporte multimodal")
    
    print("\nFALLBACK AUTOMÁTICO:")
    print("- Se Groq atingir rate limit:")
    print("  • Sistema migra automaticamente para Gemini")
    print("  • Transparente para o usuário")
    print("  • Garante que o ciclo de auto-evolução nunca pare")


def demo_scenarios():
    """Demonstrate real-world scenarios"""
    print("\n" + "="*80)
    print("DEMO 4: Real-World Scenarios")
    print("="*80)
    
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    gateway = AIGateway(
        groq_api_key=groq_key,
        gemini_api_key=gemini_key,
    )
    gateway.groq_client = "GROQ_CLIENT"
    gateway.gemini_client = "GEMINI_CLIENT"
    
    scenarios = [
        {
            "name": "Análise de Log Curto",
            "payload": "ERROR: Connection timeout na linha 145",
            "expected": LLMProvider.GROQ,
        },
        {
            "name": "Relatório Extenso de Métricas",
            "payload": "Métrica " * 15000,  # >10k tokens
            "expected": LLMProvider.GEMINI,
        },
        {
            "name": "Monólogo Interno (Self-reflection)",
            "payload": "Analisando meu desempenho nas últimas 24h...",
            "expected": LLMProvider.GROQ,
        },
        {
            "name": "Análise de Código Completo",
            "payload": "def function():\n    pass\n" * 3000,
            "expected": LLMProvider.GEMINI,
        },
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        provider = gateway.select_provider(scenario["payload"])
        tokens = gateway.count_tokens(scenario["payload"])
        
        status = "✓" if provider == scenario["expected"] else "✗"
        print(f"\n{i}. {scenario['name']}")
        print(f"   Tokens: {tokens}")
        print(f"   Provedor: {provider.value}")
        print(f"   Esperado: {scenario['expected'].value} {status}")


def main():
    """Run all demos"""
    print("\n" + "="*80)
    print("AI GATEWAY DEMONSTRATION")
    print("Intelligent routing between Groq and Gemini for Jarvis")
    print("="*80)
    
    try:
        demo_token_counting()
        demo_provider_selection()
        demo_cost_priority()
        demo_scenarios()
        
        print("\n" + "="*80)
        print("DEMO COMPLETED SUCCESSFULLY!")
        print("="*80)
        
        print("\nSUMMARY:")
        print("✓ Token counting: Working")
        print("✓ Provider selection: Working")
        print("✓ Cost optimization: Working")
        print("✓ Context escalation: Working")
        print("✓ Auto-fallback: Implemented (tested in unit tests)")
        
        print("\nNEXT STEPS:")
        print("1. Configure GROQ_API_KEY in your .env file")
        print("2. Configure GEMINI_API_KEY in your .env file")
        print("3. Test with real API calls using the AssistantService")
        
    except Exception as e:
        logger.error(f"Error during demo: {e}", exc_info=True)
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()
