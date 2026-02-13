#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de demonstração do Sistema de Evolução Marvel do Jarvis

Este script demonstra como o Jarvis:
1. Lê a Apostila de Evolução (MARVEL_ROADMAP.md)
2. Identifica a primeira habilidade Marvel não aprendida
3. Valida através do Metabolismo (testes de estresse)
4. Marca como "Aprendida" se passar nos testes
5. Reporta progresso em Português
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.application.services.marvel_evolution import MarvelEvolutionService
except ImportError as e:
    print(f"⚠️  Erro ao importar MarvelEvolutionService: {e}")
    print("   Tentando importação direta...")
    
    # Direct import for demo purposes
    import logging
    import re
    from typing import Dict, Any, Optional, List
    
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Inline version of MarvelEvolutionService for demo
    class MarvelEvolutionService:
        """Simplified version for demonstration"""
        
        MARVEL_SKILLS = {
            94: "Interface Holográfica - Antecipar Necessidades do Usuário",
            95: "Diagnóstico de Armadura - Propor Soluções Proativamente",
            96: "Controle de Periféricos - Ação Proativa e Segura",
            97: "Sistemas Integrados - Coordenar Físico e Digital",
            98: "Copiloto Cognitivo - Operar como Assistente Mental",
            99: "Alinhamento Contínuo - Manter Sintonia com Usuário",
            100: "Evolução Preservando Identidade - Evoluir sem Perder Essência",
            101: "Sustentabilidade Econômica - Autossuficiência Financeira",
            102: "Infraestrutura Cognitiva Pessoal - Fundação do Pensamento",
        }
        
        def __init__(self):
            self.roadmap_path = project_root / "docs" / "MARVEL_ROADMAP.md"
            logger.info(f"Using roadmap: {self.roadmap_path}")
        
        def find_next_marvel_skill(self):
            """Find next skill to learn"""
            if not self.roadmap_path.exists():
                return None
            
            content = self.roadmap_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            in_skills_section = False
            for i, line in enumerate(lines):
                if '## 🎯 As 9 Habilidades' in line:
                    in_skills_section = True
                    continue
                
                if in_skills_section and line.startswith('## ') and 'Habilidades' not in line:
                    break
                
                skill_match = re.match(r'^### (\d+)\.\s+(.+)$', line)
                if skill_match and in_skills_section:
                    skill_num = int(skill_match.group(1))
                    skill_name = skill_match.group(2).strip()
                    
                    # Look for status
                    for j in range(i, min(i+10, len(lines))):
                        if '**Status**:' in lines[j] and '[ ]' in lines[j]:
                            # Found first unchecked skill
                            capability_id = 93 + skill_num
                            return {
                                'skill': {
                                    'number': skill_num,
                                    'name': skill_name,
                                    'capability_id': capability_id,
                                    'status': 'not_learned'
                                },
                                'description': 'Demo skill',
                                'requirements': ['Req 1', 'Req 2'],
                                'acceptance_criteria': ['Test 1', 'Test 2'],
                                'scripts_needed': ['script1.py', 'test_script1.py']
                            }
            return None
        
        def get_marvel_progress(self):
            """Get progress statistics"""
            if not self.roadmap_path.exists():
                return {'error': 'Roadmap not found'}
            
            content = self.roadmap_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            
            learned = sum(1 for line in lines if re.match(r'- \[x\] Habilidade \d+:', line, re.IGNORECASE))
            total = 9
            
            return {
                'total_skills': total,
                'learned': learned,
                'not_learned': total - learned,
                'progress_percentage': (learned / total * 100) if total > 0 else 0,
                'level': 'Marvel' if learned == total else 'Em Progresso'
            }
        
        def is_skill_validated_by_metabolismo(self, skill_number, test_results):
            """Validate skill with test results"""
            if not test_results:
                return False
            passed = test_results.get('passed', 0)
            total = test_results.get('total', 0)
            return passed == total if total > 0 else False
        
        def generate_progress_report(self, skill_name, tests_passed, tests_total, learning_time="N/A"):
            """Generate progress report"""
            progress = self.get_marvel_progress()
            if 'error' in progress:
                return f"❌ Erro: {progress['error']}"
            
            learned = progress['learned']
            total = progress['total_skills']
            percentage = progress['progress_percentage']
            
            report = f"""
🤖 Comandante, mais uma habilidade do Jarvis Marvel foi integrada ao meu DNA.

Habilidade Aprendida: {skill_name}
Testes Passaram: {tests_passed}/{tests_total} ({tests_passed/tests_total*100:.0f}%)
Tempo de Aprendizado: {learning_time}

📈 Progresso Geral: {learned}/{total} habilidades Marvel ({percentage:.1f}% completo)
Estamos {percentage:.1f}% mais próximos do Xerife Marvel.
"""
            
            if learned < total:
                next_skill = self.find_next_marvel_skill()
                if next_skill:
                    report += f"\nPróxima Missão: {next_skill['skill']['name']}\n"
            else:
                report += "\n🎉 TODAS AS HABILIDADES MARVEL FORAM APRENDIDAS!\n"
            
            return report.strip()


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def main():
    print_section("🧬 DEMONSTRAÇÃO: SISTEMA DE EVOLUÇÃO MARVEL DO JARVIS")
    
    # Initialize Marvel Evolution Service
    print("\n1️⃣ Inicializando MarvelEvolutionService...")
    marvel_service = MarvelEvolutionService()
    print(f"   ✅ Serviço inicializado")
    print(f"   📄 Apostila: {marvel_service.roadmap_path.name}")
    
    # Get current progress
    print("\n2️⃣ Verificando progresso atual...")
    progress = marvel_service.get_marvel_progress()
    
    if 'error' in progress:
        print(f"   ❌ Erro: {progress['error']}")
        return
    
    print(f"   📊 Progresso Marvel:")
    print(f"      Total de Habilidades: {progress['total_skills']}")
    print(f"      Aprendidas: {progress['learned']}")
    print(f"      Não Aprendidas: {progress['not_learned']}")
    print(f"      Progresso: {progress['progress_percentage']:.1f}%")
    print(f"      Nível: {progress['level']}")
    
    # Find next skill to learn
    print("\n3️⃣ Buscando próxima habilidade Marvel para aprender...")
    next_skill = marvel_service.find_next_marvel_skill()
    
    if next_skill is None:
        print("   🎉 Todas as habilidades Marvel já foram aprendidas!")
        print("   🏆 Jarvis atingiu o nível Marvel completo!")
        return
    
    skill_info = next_skill['skill']
    print(f"   ✅ Habilidade encontrada!")
    print(f"      Número: {skill_info['number']}")
    print(f"      Nome: {skill_info['name']}")
    print(f"      ID da Capacidade: {skill_info['capability_id']}")
    print(f"      Status: {skill_info['status']}")
    
    # Show skill details
    print("\n4️⃣ Detalhes da Habilidade:")
    print(f"   📝 Descrição: {next_skill['description']}")
    
    print(f"\n   🎯 Habilidades Necessárias ({len(next_skill['requirements'])}):")
    for i, req in enumerate(next_skill['requirements'], 1):
        print(f"      {i}. {req}")
    
    print(f"\n   ✅ Critérios de Aprovação (Metabolismo) ({len(next_skill['acceptance_criteria'])}):")
    for i, criterion in enumerate(next_skill['acceptance_criteria'], 1):
        print(f"      {i}. {criterion}")
    
    print(f"\n   📁 Scripts Necessários ({len(next_skill['scripts_needed'])}):")
    for i, script in enumerate(next_skill['scripts_needed'], 1):
        print(f"      {i}. {script}")
    
    # Simulate learning cycle
    print_section("🔄 SIMULAÇÃO DO CICLO DE APRENDIZADO")
    
    print("\n5️⃣ Ciclo de Estudo e Execução:")
    print("   📚 1. Lendo requisitos da habilidade...")
    print("   💻 2. Buscando ou criando scripts necessários...")
    print("   🧪 3. Executando Metabolismo (testes de estresse)...")
    
    # Simulate test results
    print("\n6️⃣ Resultados do Metabolismo:")
    print("   🧬 Executando pytest para validação...")
    
    # Example 1: All tests pass
    print("\n   Cenário 1: Todos os testes passam ✅")
    test_results_success = {
        'passed': 4,
        'total': 4,
        'success_rate': 100.0
    }
    
    is_valid = marvel_service.is_skill_validated_by_metabolismo(
        skill_info['number'], 
        test_results_success
    )
    
    print(f"   Testes: {test_results_success['passed']}/{test_results_success['total']} passaram")
    print(f"   Taxa de Sucesso: {test_results_success['success_rate']}%")
    print(f"   Validação: {'✅ APROVADO' if is_valid else '❌ REPROVADO'}")
    
    if is_valid:
        print(f"\n   🎯 Habilidade {skill_info['number']} pode ser marcada como Aprendida!")
        
        # Generate progress report
        print("\n7️⃣ Relatório de Progresso:")
        report = marvel_service.generate_progress_report(
            skill_name=skill_info['name'],
            tests_passed=test_results_success['passed'],
            tests_total=test_results_success['total'],
            learning_time="2 horas"
        )
        print(report)
    
    # Example 2: Some tests fail
    print("\n" + "-" * 70)
    print("\n   Cenário 2: Alguns testes falham ❌")
    test_results_fail = {
        'passed': 2,
        'total': 4,
        'success_rate': 50.0
    }
    
    is_valid = marvel_service.is_skill_validated_by_metabolismo(
        skill_info['number'], 
        test_results_fail
    )
    
    print(f"   Testes: {test_results_fail['passed']}/{test_results_fail['total']} passaram")
    print(f"   Taxa de Sucesso: {test_results_fail['success_rate']}%")
    print(f"   Validação: {'✅ APROVADO' if is_valid else '❌ REPROVADO'}")
    
    if not is_valid:
        print(f"\n   ⚠️  Habilidade {skill_info['number']} NÃO pode ser marcada como Aprendida")
        print("   🔄 Jarvis deve revisar a implementação e tentar novamente")
    
    # Show Marvel skills mapping
    print_section("📚 MAPEAMENTO DAS 9 HABILIDADES MARVEL")
    
    print("\nTodas as 9 habilidades Marvel:")
    for cap_id, skill_name in MarvelEvolutionService.MARVEL_SKILLS.items():
        skill_num = cap_id - 93
        is_current = skill_num == skill_info['number']
        marker = "👉" if is_current else "  "
        print(f"{marker} {skill_num}. {skill_name} (ID: {cap_id})")
    
    # Summary
    print_section("📊 RESUMO")
    
    print(f"""
✨ O Sistema de Evolução Marvel está funcionando corretamente!

Próximos Passos:
1. Implementar os scripts necessários para a habilidade atual
2. Escrever testes de validação (Metabolismo)
3. Executar pytest para validar
4. Se aprovado, marcar como [x] Aprendida no MARVEL_ROADMAP.md
5. Gerar relatório de progresso para o Comandante
6. Repetir para as próximas 8 habilidades

Meta Final: Jarvis Marvel com 100% de habilidades aprendidas! 🎯
""")


if __name__ == "__main__":
    main()
