# -*- coding: utf-8 -*-
import argparse
import os
import sys
import json
from pathlib import Path
# Importamos o Core para centralizar as chamadas de IA
from app.application.services.metabolism_core import MetabolismCore

def evolve():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strategy', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--impact', required=True)
    parser.add_argument('--roadmap-context', default="")
    args = parser.parse_args()

    core = MetabolismCore()
    # O ISSUE_BODY agora contém "ID: Título" vindo do YML V2
    issue_body = os.getenv('ISSUE_BODY', 'Nova funcionalidade')

    # --- PASSO 1: ARQUITETURA ESTRUTURADA ---
    system_arch = (
        "Você é o Arquiteto Senior do ecossistema JARVIS.\n"
        "Sua missão é traduzir uma capacidade técnica do inventário JSON em alterações de código.\n"
        "DIRETRIZES DE DIRETÓRIO:\n"
        "- Lógica de Negócio: 'app/application/services/'\n"
        "- Infraestrutura/Drivers: 'app/adapters/infrastructure/'\n"
        "- Utilitários: 'app/core/' ou 'scripts/'\n"
        "Responda APENAS JSON: {'target_file': 'caminho/arquivo.py', 'reason': 'explicação'}"
    )
    
    user_arch = f"""
    MISSÃO: {issue_body}
    CONTEXTO TÉCNICO (JSON Inventory):
    {args.roadmap_context}
    
    Analise as dependências e notas para decidir o melhor local de implementação.
    """

    try:
        print(f"🧠 JARVIS analisando arquitetura para: {issue_body}...")
        arch_decision = core.ask_jarvis(system_arch, user_arch)
        target_file = arch_decision.get('target_file')
        
        if not target_file:
            raise ValueError("O Arquiteto não definiu um 'target_file'.")

        path = Path(target_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        current_code = path.read_text(encoding='utf-8') if path.exists() else "# Componente recém-criado pelo ciclo de auto-evolução JARVIS"

        # --- PASSO 2: ENGENHARIA E MUTAÇÃO ---
        system_eng = (
            "Você é o Engenheiro Senior do JARVIS.\n"
            "Implemente a capacidade técnica solicitada seguindo padrões de código limpo e alta performance.\n"
            "Responda APENAS JSON: {'code': 'código completo e funcional', 'summary': 'resumo técnico'}"
        )
        
        user_eng = f"""
        OBJETIVO: {issue_body}
        ARQUIVO ALVO: {target_file}
        CÓDIGO ATUAL:
        {current_code}
        
        CONDIÇÃO: Se o arquivo já existe, mantenha a estrutura atual e adicione a nova funcionalidade.
        Se for novo, crie a classe/função necessária.
        """

        print(f"🧬 Gerando mutação de DNA em: {target_file}")
        mutation = core.ask_jarvis(system_eng, user_eng)

        new_code = mutation.get('code', '')
        summary = mutation.get('summary', 'Evolução aplicada com sucesso.')

        if len(new_code.strip()) > 20:
            path.write_text(new_code, encoding='utf-8')
            # Salvamos o resumo para o GitHub Actions ler e colocar no corpo do PR
            Path("mutation_summary.txt").write_text(str(summary), encoding='utf-8')
            print(f"✅ Evolução Concluída: {target_file}")
        else:
            print("❌ Erro: O código gerado é insuficiente ou vazio.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Falha Crítica no Ciclo de Evolução: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    evolve()
