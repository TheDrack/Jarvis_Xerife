# -*- coding: utf-8 -*-
"""
JARVIS - Ponto de Entrada Principal (Ignição)
Seguindo o Protocolo de Simbiose: "Operamos como um só."
"""

import os
import sys
from app.core.nexus import nexus

def bootstrap():
    """
    Prepara a carga e o destino. 
    O Nexus fornece o veículo (Componentes) e o trajeto (Orquestração).
    """
    print("\n" + "="*50)
    print("  JARVIS - PROTOCOLO DE IGNIÇÃO INICIADO")
    print("="*50)

    try:
        # 1. Resolver o Orquestrador (Isso dispara o discovery automático do Nexus)
        # O Nexus já sabe olhar no seu disco e no Gist para achar o orchestrator_service.
        orchestrator = nexus.resolve("orchestrator_service")
        
        # 2. Capturar Ordem Inicial
        user_order = input("\n👤 Senhor, qual a sua ordem? ")

        # 3. Preparar Contexto de Execução
        context = {
            "input_text": user_order,
            "metadata": {
                "session_id": "jarvis_session_001",
                "timestamp": time.time() if 'time' in sys.modules else None
            }
        }

        # 4. Execução Incondicional
        # O Orquestrador resolve internamente o Assistant, LLM e ActionProvider via Nexus.
        result = orchestrator.execute(context)

        # 5. Saída e Sincronização
        if result.get("success"):
            # O Nexus salva qualquer alteração no DNA (Gist) automaticamente antes de fechar
            nexus.commit_memory()
            print(f"\n🤖 [JARVIS]: {result.get('result', 'Missão cumprida.')}")
        else:
            print(f"\n💥 [ERRO]: {result.get('error')}")

    except Exception as e:
        print(f"❌ FALHA CRÍTICA NO BOOTSTRAP: {e}")
        sys.exit(1)

if __name__ == "__main__":
    bootstrap()
