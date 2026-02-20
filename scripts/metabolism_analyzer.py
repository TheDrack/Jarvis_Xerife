import os
import sys
import json
import argparse
from app.application.services.auto_evolution import AutoEvolutionService

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent", type=str, required=True)
    parser.add_argument("--repo-path", type=str, default=".")
    args = parser.parse_args()

    auto = AutoEvolutionService()
    
    try:
        # 1. ANALISAR RISCO DA MUTAÇÃO/EVOLUÇÃO
        # O Analyzer consulta a LLM para validar se o código alterado ou a missão
        # do Roadmap é crítica (DNA central) ou operacional (periferia).
        analysis_result = auto.analyze_impact(intent=args.intent, repo_path=args.repo_path)
        
        # 2. OUTPUT PARA O CI/CD
        # O Workflow (homeostasis.yml) espera ler este JSON para decidir o Auto-Merge
        print(json.dumps(analysis_result, indent=2))
        
        # Se houver erro crítico na análise, sai com erro
        if not analysis_result:
            sys.exit(1)
            
    except Exception as e:
        # Em caso de erro, por segurança, exige intervenção humana
        error_result = {
            "requires_human": True,
            "risk_level": "critical",
            "reason": f"Analyzer Error: {str(e)}"
        }
        print(json.dumps(error_result))
        sys.exit(0) # Saída 0 para o log ser lido, mas requer_human impede o merge

if __name__ == "__main__":
    main()
