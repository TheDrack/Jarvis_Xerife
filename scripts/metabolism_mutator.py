import os
import sys
import json
import argparse
from app.application.services.auto_evolution import AutoEvolutionService

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", type=str, default="minimal_change")
    parser.add_argument("--intent", type=str, required=True)
    parser.add_argument("--roadmap-context", type=str, default="")
    args = parser.parse_args()

    auto = AutoEvolutionService()
    
    # 1. LÓGICA DE AUTO-CURA (FIX TEST FAILURE)
    if args.intent == "fix-test-failure":
        print("🔧 Iniciando protocolo de Auto-Cura...")
        report_path = "report.json"
        error_context = ""
        
        if os.path.exists(report_path):
            with open(report_path, 'r') as f:
                report = json.load(f)
                # Extrai apenas falhas para o contexto
                failures = [test for test in report.get("tests", []) if test.get("outcome") == "failed"]
                error_context = json.dumps(failures, indent=2)
        
        # Aqui o Mutador chama a LLM passando o código + error_context
        # (A lógica de chamada à LLM já existe no seu CORE_LOGIC)
        success = auto.apply_mutation(intent=args.intent, context=error_context)
        sys.exit(0 if success else 1)

    # 2. LÓGICA DE AUTO-EVOLUÇÃO (ROADMAP)
    elif args.intent == "auto-evolution-mission":
        print("🧬 Iniciando evolução via Roadmap...")
        mission_data = auto.find_next_mission_with_auto_complete()
        
        if not mission_data:
            print("📭 Nenhuma missão pendente.")
            sys.exit(0)

        mission_desc = mission_data['mission']['description']
        context = auto.get_roadmap_context(mission_data)
        
        # Cria branch para a evolução
        branch_name = f"auto-evolution/mission-{os.popen('date +%s').read().strip()}"
        os.system(f"git checkout -b {branch_name}")
        
        # Executa a mutação no código
        success = auto.apply_mutation(intent=mission_desc, context=context)
        
        if success:
            # Commit das alterações (ignorando logs)
            os.system("git add -A && git reset .github/metabolism_logs/")
            if os.popen("git status --porcelain").read().strip():
                os.system(f"git config user.name 'Jarvis-AutoEvolution'")
                os.system(f"git config user.email 'jarvis@bot.com'")
                os.system(f"git commit -m '[Auto-Evolution] DNA Mutated: {mission_desc}'")
                os.system(f"git push origin {branch_name}")
                print(f"✅ Mutação aplicada na branch {branch_name}")
            else:
                print("⚠️ Nenhuma mudança de código gerada.")
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
