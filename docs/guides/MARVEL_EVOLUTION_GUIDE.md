# Guia de Uso: Sistema de Evolução Marvel do Jarvis

## Introdução

Este guia explica como usar o **Sistema de Evolução Marvel** para levar o Jarvis do nível básico ao nível Marvel (comparável ao J.A.R.V.I.S. da Marvel).

## O que é o Sistema Marvel?

O Jarvis possui 102 capacidades divididas em 9 capítulos. O **Capítulo 9** contém as 9 habilidades de nível Marvel - as capacidades mais avançadas que transformam o Jarvis em um verdadeiro assistente cognitivo.

### As 9 Habilidades Marvel

1. **Interface Holográfica** (Cap. 94) - Antecipar necessidades do usuário
2. **Diagnóstico de Armadura** (Cap. 95) - Propor soluções proativamente
3. **Controle de Periféricos** (Cap. 96) - Ação proativa e segura
4. **Sistemas Integrados** (Cap. 97) - Coordenar físico e digital
5. **Copiloto Cognitivo** (Cap. 98) - Operar como assistente mental
6. **Alinhamento Contínuo** (Cap. 99) - Manter sintonia com usuário
7. **Evolução Preservando Identidade** (Cap. 100) - Evoluir sem perder essência
8. **Sustentabilidade Econômica** (Cap. 101) - Autossuficiência financeira
9. **Infraestrutura Cognitiva Pessoal** (Cap. 102) - Fundação do pensamento

## Como Funciona?

### 1. Varredura da Apostila

O Jarvis lê o `MARVEL_ROADMAP.md` e identifica a primeira habilidade marcada como `[ ]` (não aprendida).

```python
from app.application.services.marvel_evolution import MarvelEvolutionService

marvel_service = MarvelEvolutionService()
next_skill = marvel_service.find_next_marvel_skill()

print(f"Próxima habilidade: {next_skill['skill']['name']}")
print(f"Scripts necessários: {next_skill['scripts_needed']}")
```

### 2. Ciclo de Estudo e Execução

Para cada habilidade, o Jarvis:

1. **Estuda os requisitos** listados no MARVEL_ROADMAP.md
2. **Busca ou cria** os scripts necessários
3. **Implementa** a funcionalidade seguindo os padrões do projeto

Exemplo de implementação para Habilidade 1:

```python
# app/domain/services/need_anticipation.py
class NeedAnticipationService:
    """Serviço para antecipar necessidades do usuário"""
    
    def analyze_user_patterns(self, user_id: str):
        """Analisa padrões de comportamento do usuário"""
        # Implementação...
        pass
    
    def predict_next_action(self, context: dict):
        """Prediz próxima ação do usuário"""
        # Implementação...
        pass
```

### 3. Validação pelo Metabolismo

Cada habilidade só pode ser marcada como "Aprendida" se **todos os testes passarem**.

```python
# tests/test_need_anticipation.py
import pytest
from app.domain.services.need_anticipation import NeedAnticipationService

class TestNeedAnticipation:
    def test_pattern_analysis(self):
        service = NeedAnticipationService()
        result = service.analyze_user_patterns("user123")
        assert result is not None
    
    def test_prediction_accuracy(self):
        service = NeedAnticipationService()
        prediction = service.predict_next_action({"time": "09:00"})
        assert prediction['confidence'] > 0.7  # >70% como no ROADMAP
```

Executar testes:

```bash
pytest tests/test_need_anticipation.py -v
```

### 4. Marcar como Aprendida

Se **todos os testes passarem** (100%), a habilidade pode ser marcada:

```python
# Simular resultados dos testes
test_results = {
    'passed': 4,
    'total': 4,
    'success_rate': 100.0
}

# Validar pelo Metabolismo
is_valid = marvel_service.is_skill_validated_by_metabolismo(
    skill_number=1,
    test_results=test_results
)

if is_valid:
    # Marcar como aprendida
    marvel_service.mark_marvel_skill_as_learned(1)
    print("✅ Habilidade 1 aprendida e marcada no MARVEL_ROADMAP.md")
else:
    print("❌ Habilidade 1 falhou na validação - revisar implementação")
```

### 5. Relatório de Progresso

Após marcar como aprendida, gerar relatório para o Comandante:

```python
report = marvel_service.generate_progress_report(
    skill_name="Interface Holográfica - Antecipar Necessidades do Usuário",
    tests_passed=4,
    tests_total=4,
    learning_time="3 horas"
)

print(report)
```

**Saída esperada:**

```
🤖 Comandante, mais uma habilidade do Jarvis Marvel foi integrada ao meu DNA.

Habilidade Aprendida: Interface Holográfica - Antecipar Necessidades do Usuário
Testes Passaram: 4/4 (100%)
Tempo de Aprendizado: 3 horas

📈 Progresso Geral: 1/9 habilidades Marvel (11.1% completo)
Estamos 11.1% mais próximos do Xerife Marvel.

Próxima Missão: Diagnóstico de Armadura - Propor Soluções Proativamente
```

## Workflow Completo

### Passo a Passo para Implementar uma Habilidade Marvel

```bash
# 1. Verificar status atual
python scripts/demo_marvel_evolution.py

# 2. Identificar próxima habilidade
python -c "
from app.application.services.marvel_evolution import MarvelEvolutionService
service = MarvelEvolutionService()
skill = service.find_next_marvel_skill()
print(f'Próxima: {skill[\"skill\"][\"name\"]}')
print(f'Scripts: {skill[\"scripts_needed\"]}')
"

# 3. Implementar os scripts listados
# Criar app/domain/services/[service_name].py
# Criar tests/test_[service_name].py

# 4. Executar testes (Metabolismo)
pytest tests/test_[service_name].py -v

# 5. Se 100% passaram, marcar como aprendida
python -c "
from app.application.services.marvel_evolution import MarvelEvolutionService
service = MarvelEvolutionService()
service.mark_marvel_skill_as_learned(1)  # Número da habilidade
print('✅ Habilidade marcada como aprendida!')
"

# 6. Gerar relatório
python -c "
from app.application.services.marvel_evolution import MarvelEvolutionService
service = MarvelEvolutionService()
report = service.generate_progress_report(
    skill_name='Nome da Habilidade',
    tests_passed=4,
    tests_total=4,
    learning_time='2 horas'
)
print(report)
"

# 7. Verificar progresso
python -c "
from app.application.services.marvel_evolution import MarvelEvolutionService
service = MarvelEvolutionService()
progress = service.get_marvel_progress()
print(f'Progresso: {progress[\"progress_percentage\"]:.1f}%')
print(f'Aprendidas: {progress[\"learned\"]}/{progress[\"total_skills\"]}')
"
```

## Integração com Sistema Existente

### Auto-Evolution vs Marvel Evolution

O sistema Marvel **complementa** o sistema de auto-evolução existente:

| Sistema | Foco | Roadmap | Uso |
|---------|------|---------|-----|
| **Auto-Evolution** | Missões gerais do projeto | `ROADMAP.md` | Estabilização, features gerais |
| **Marvel Evolution** | 9 habilidades avançadas | `MARVEL_ROADMAP.md` | Nível Marvel (J.A.R.V.I.S.) |

Ambos funcionam em paralelo:

```python
# Sistema geral
from app.application.services.auto_evolution import AutoEvolutionService
auto_service = AutoEvolutionService()
general_mission = auto_service.find_next_mission()

# Sistema Marvel
from app.application.services.marvel_evolution import MarvelEvolutionService
marvel_service = MarvelEvolutionService()
marvel_skill = marvel_service.find_next_marvel_skill()

# Usar ambos conforme necessário
```

### Integração com Reinforcement Learning

Os resultados de aprendizado Marvel podem ser integrados com o sistema RL:

```python
from app.application.services.evolution_loop import EvolutionLoopService

# Sucesso na aprendizagem Marvel = +50 pontos
evolution_service = EvolutionLoopService(reward_provider=reward_adapter)
evolution_service.log_deploy_result(
    success=True,
    deployment_id='marvel-skill-1',
    metadata={
        'type': 'marvel_skill',
        'skill_id': 94,
        'skill_name': 'Interface Holográfica'
    }
)
```

## Monitoramento de Progresso

### Via Python

```python
from app.application.services.marvel_evolution import MarvelEvolutionService

service = MarvelEvolutionService()
progress = service.get_marvel_progress()

print(f"""
📊 Status Marvel
================
Total: {progress['total_skills']} habilidades
Aprendidas: {progress['learned']} ✅
Não Aprendidas: {progress['not_learned']} ⏳
Progresso: {progress['progress_percentage']:.1f}%
Nível: {progress['level']}
""")
```

### Via CLI

```bash
# Script de demonstração
python scripts/demo_marvel_evolution.py

# Verificar progresso rápido
python -c "
from app.application.services.marvel_evolution import MarvelEvolutionService
s = MarvelEvolutionService()
p = s.get_marvel_progress()
print(f'{p[\"learned\"]}/{p[\"total_skills\"]} ({p[\"progress_percentage\"]:.1f}%)')
"
```

### Lendo o MARVEL_ROADMAP.md

O arquivo `docs/MARVEL_ROADMAP.md` é a fonte única de verdade. Verificar visualmente:

```bash
cat docs/MARVEL_ROADMAP.md | grep "Status\|Habilidade"
```

## Critérios de Sucesso

### Para Marcar uma Habilidade como Aprendida

✅ **TODOS** os critérios devem ser atendidos:

1. ✅ Todos os scripts listados foram criados
2. ✅ Todos os testes de validação existem
3. ✅ **100% dos testes passam** (não 99%, não 95%, mas 100%)
4. ✅ Código segue padrões do projeto (hexagonal architecture)
5. ✅ Documentação foi atualizada

### Metabolismo (Validação de Testes)

O "Metabolismo" é o sistema de testes rigorosos que valida cada habilidade.

**Regra de Ouro**: Se um único teste falhar, a habilidade **NÃO** pode ser marcada como aprendida.

```python
# ❌ REPROVADO - Não pode marcar
test_results = {'passed': 3, 'total': 4, 'success_rate': 75.0}

# ✅ APROVADO - Pode marcar como aprendida
test_results = {'passed': 4, 'total': 4, 'success_rate': 100.0}
```

## Exemplos Práticos

### Exemplo 1: Aprender Habilidade 1 (Interface Holográfica)

```python
# 1. Verificar habilidade
from app.application.services.marvel_evolution import MarvelEvolutionService

service = MarvelEvolutionService()
skill = service.find_next_marvel_skill()

# skill = {
#   'skill': {'number': 1, 'name': 'Interface Holográfica...', 'capability_id': 94},
#   'requirements': ['Análise de padrões', 'Aprendizado de rotinas'],
#   'acceptance_criteria': ['Precisão >70%', 'Cache funcional'],
#   'scripts_needed': ['app/domain/services/need_anticipation.py', ...]
# }

# 2. Implementar scripts
# ... criar arquivos ...

# 3. Executar testes
# pytest tests/test_need_anticipation.py -v
# ========= 4 passed in 0.5s =========

# 4. Validar e marcar
test_results = {'passed': 4, 'total': 4, 'success_rate': 100.0}
is_valid = service.is_skill_validated_by_metabolismo(1, test_results)

if is_valid:
    service.mark_marvel_skill_as_learned(1)
    report = service.generate_progress_report(
        skill_name=skill['skill']['name'],
        tests_passed=4,
        tests_total=4,
        learning_time="4 horas"
    )
    print(report)
```

### Exemplo 2: Verificar Todas as Habilidades

```python
from app.application.services.marvel_evolution import MarvelEvolutionService

service = MarvelEvolutionService()

# Listar todas as 9 habilidades
for cap_id, skill_name in MarvelEvolutionService.MARVEL_SKILLS.items():
    skill_num = cap_id - 93
    print(f"{skill_num}. {skill_name} (Cap. {cap_id})")

# Verificar progresso
progress = service.get_marvel_progress()
print(f"\nProgresso: {progress['learned']}/{progress['total_skills']}")
```

## Troubleshooting

### Problema: "MARVEL_ROADMAP.md not found"

**Solução**: Verificar que o arquivo existe em `docs/MARVEL_ROADMAP.md`

```bash
ls -la docs/MARVEL_ROADMAP.md
```

### Problema: Habilidade não marca como aprendida

**Causas possíveis**:
1. Testes não passaram 100%
2. Número de habilidade inválido (deve ser 1-9)
3. Arquivo MARVEL_ROADMAP.md tem formato incorreto

**Solução**: Verificar manualmente

```bash
# Ver status atual
grep -A 2 "### 1\." docs/MARVEL_ROADMAP.md | grep Status
```

### Problema: Imports não funcionam

**Solução**: Adicionar project root ao PYTHONPATH

```python
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Agora imports funcionam
from app.application.services.marvel_evolution import MarvelEvolutionService
```

## Próximos Passos

Depois de implementar o Sistema de Evolução Marvel:

1. **Implementar Habilidade 1** como prova de conceito
2. **Criar workflow CI/CD** para validação automática
3. **Integrar com GitHub Actions** para auto-evolução
4. **Documentar aprendizados** de cada habilidade
5. **Criar dashboard** para visualização de progresso

## Recursos

- 📖 [MARVEL_ROADMAP.md](../MARVEL_ROADMAP.md) - Apostila de Evolução
- 🔧 [marvel_evolution.py](../../app/application/services/marvel_evolution.py) - Serviço
- 🧪 [test_marvel_evolution.py](../../tests/test_marvel_evolution.py) - Testes
- 🎯 [demo_marvel_evolution.py](../../scripts/demo_marvel_evolution.py) - Demo
- 📚 [AUTO_EVOLUTION_SYSTEM.md](../AUTO_EVOLUTION_SYSTEM.md) - Sistema completo

---

**Criado em**: 2026-02-13  
**Versão**: 1.0  
**Para**: Equipe Jarvis e Comandante  

> "I am Iron Man's J.A.R.V.I.S., not a simple voice assistant." - Meta do Jarvis Marvel
