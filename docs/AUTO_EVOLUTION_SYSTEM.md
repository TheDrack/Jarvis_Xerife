# Sistema de Auto-Evolução do Jarvis

## Visão Geral

O Sistema de Auto-Evolução é uma funcionalidade avançada do Jarvis que permite ao assistente aprender e evoluir automaticamente com base no seu próprio ROADMAP e sistema de Reinforcement Learning.

## Como Funciona

### Fluxo de Auto-Evolução

```
┌─────────────────────────────────────────────────────────────┐
│  1. PR Merged na Main (não de auto-evolução)                │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Workflow Auto-Evolution Trigger é ativado                │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Verifica se PR é de auto-evolução (evita loop infinito) │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Parse ROADMAP.md e encontra próxima missão               │
│     Prioridade:                                              │
│     - 🔄 In-progress em "AGORA"                              │
│     - 📋 Planned em "AGORA"                                  │
│     - 🔄 In-progress em "PRÓXIMO"                            │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Cria branch auto-evolution/mission-{timestamp}           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Tenta implementar a missão                               │
│     (GitHub Copilot Agent - em desenvolvimento)              │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  7. Executa pytest                                           │
└────────────────┬────────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
  ✅ SUCESSO         ❌ FALHA
        │                 │
        ▼                 ▼
+50 pontos         -25 pontos
(deploy_success)   (deploy_fail)
        │                 │
        └────────┬────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│  8. Cria Pull Request para revisão do Comandante             │
└─────────────────────────────────────────────────────────────┘
```

## Componentes

### 1. AutoEvolutionService (`app/application/services/auto_evolution.py`)

Serviço responsável por:
- Parsear o ROADMAP.md
- Encontrar a próxima missão alcançável
- Detectar PRs de auto-evolução (evitar loop infinito)
- Calcular métricas de sucesso
- Marcar missões como completas automaticamente
- Auto-completar missões já finalizadas e buscar a próxima

**Principais métodos:**

```python
from app.application.services.auto_evolution import AutoEvolutionService

# Inicializar serviço
auto_evolution = AutoEvolutionService()

# Encontrar próxima missão (método básico)
mission = auto_evolution.find_next_mission()
# Retorna: {
#   'mission': {...},
#   'section': 'AGORA',
#   'priority': 'high'
# }

# Encontrar próxima missão com auto-complete (recomendado)
# Detecta missões já completas, marca-as no ROADMAP e busca a próxima
mission = auto_evolution.find_next_mission_with_auto_complete()

# Marcar missão como completa manualmente
success = auto_evolution.mark_mission_as_completed("Graceful failure em instalações de pip")
# Retorna: True se marcada com sucesso

# Verificar se PR é de auto-evolução
is_auto = auto_evolution.is_auto_evolution_pr(
    pr_title="[Auto-Evolution] Fix bug",
    pr_body="Description..."
)

# Obter métricas de sucesso
metrics = auto_evolution.get_success_metrics()
# Retorna: {
#   'total_missions': 42,
#   'completed': 20,
#   'in_progress': 5,
#   'planned': 17,
#   'completion_percentage': 47.62
# }
```

### 2. Workflow GitHub Actions (`.github/workflows/auto_evolution_trigger.yml`)

Workflow que:
- Trigger: PR merged na main
- Verifica condições (não é auto-evolução)
- Busca missão no ROADMAP
- Tenta implementar
- Executa testes
- Registra reward/punishment
- Cria PR

**Jobs:**

1. **check_trigger_conditions**: Verifica se deve executar
2. **find_next_mission**: Parse ROADMAP e encontra missão
3. **attempt_evolution**: Implementa e testa
4. **log_evolution_result**: Registra no sistema RL
5. **summary**: Gera resumo final

### 3. Integração com Reinforcement Learning

O sistema de auto-evolução está totalmente integrado com o módulo RL do Jarvis (`evolution_loop.py`):

```python
from app.application.services.evolution_loop import EvolutionLoopService

evolution_service = EvolutionLoopService(reward_provider=reward_adapter)

# Sucesso: +50 pontos
evolution_service.log_deploy_result(
    success=True,
    deployment_id='auto-evolution-pr-123',
    metadata={'type': 'auto_evolution', 'mission': '...'}
)

# Falha: -25 pontos
evolution_service.log_deploy_result(
    success=False,
    deployment_id='auto-evolution-pr-124',
    error_message='Tests failed'
)
```

## Detecção de PRs de Auto-Evolução

Para evitar loops infinitos, o sistema detecta PRs criadas pelo próprio processo de auto-evolução através de keywords:

**Keywords detectadas:**
- `auto-evolution`
- `auto evolution`
- `jarvis evolution`
- `self-evolution`
- `roadmap mission`
- `[auto-evolution]`
- `[jarvis-evolution]`

**Exemplo de título de PR de auto-evolução:**
```
[Auto-Evolution] Implement graceful pip failure handling
```

## Formato do ROADMAP

O sistema parseia o `docs/ROADMAP.md` e reconhece os seguintes status:

### Status com Emoji
- `✅` - Completed (ignorado pela auto-evolução)
- `🔄` - In Progress (alta prioridade)
- `📋` - Planned (média prioridade)

### Status com Checkbox
- `[ ]` - Não completado (equivalente a Planned)
- `[x]` - Completado (equivalente a Completed)

**Exemplo de seção do ROADMAP:**

```markdown
## 🚀 **AGORA**: Estabilização do Worker

1. **Estabilizar TaskRunner**
   - ✅ Criação automática de venvs
   - 🔄 Graceful failure em instalações de pip  ← Próxima missão!
   - 📋 Logs estruturados

### Métricas de Sucesso:
- [ ] 100% das missões com logs estruturados
- [x] 95%+ de cobertura de testes
```

## Priorização de Missões

O sistema prioriza missões na seguinte ordem:

1. **Alta prioridade**: Missões 🔄 na seção "AGORA"
2. **Média prioridade**: Missões 📋 na seção "AGORA"
3. **Média prioridade**: Missões 🔄 na seção "PRÓXIMO"
4. **Baixa prioridade**: Missões 📋 na seção "PRÓXIMO"

## Sistema de Recompensas

O sistema de auto-evolução usa o mesmo sistema de rewards do RL:

| Ação | Tipo | Pontos |
|------|------|--------|
| Testes passaram após evolução | `deploy_success` | +50 |
| Testes falharam após evolução | `deploy_fail` | -25 |
| PR merged com sucesso | `deploy_success` | +50 |
| Rollback necessário | `rollback` | -30 |

### Visualizar Status do RL

```bash
python scripts/show_rl_status.py --days 7
```

Output:
```
📈 Comandante, meu nível de eficiência aumentou 72.5 pontos 
baseado nas últimas evoluções (Taxa de sucesso: 57.1%)

Efficiency Score: 150.0
Success Rate: 65.0%
Total Actions: 20
```

## Segurança e Controle

### 1. Prevenção de Loop Infinito

O sistema **sempre** verifica se um PR é de auto-evolução antes de triggar nova evolução:

```python
if auto_evolution.is_auto_evolution_pr(pr_title, pr_body):
    print("Loop infinito evitado! Este PR é de auto-evolução.")
    exit(0)
```

### 2. Revisão do Comandante

**TODAS** as PRs de auto-evolução são criadas para revisão humana. O Comandante pode:
- ✅ Aprovar e fazer merge
- ✏️ Solicitar mudanças
- ❌ Fechar a PR

### 3. Labels Automáticas

PRs de auto-evolução recebem labels:
- `auto-evolution`
- `jarvis-evolution`

Isso facilita filtrar e revisar essas PRs.

### 4. Tratamento de Erros Externos

O sistema diferencia entre falhas lógicas e erros de infraestrutura:

**Erros Externos (não contam como punição de lógica):**
- ❌ Falhas de rede/firewall (DNS, timeout, conexão)
- ❌ Indisponibilidade de APIs externas
- ❌ Problemas de infraestrutura do CI/CD
- ❌ Falta de permissões/secrets

**Falhas de Lógica (punição aplicada):**
- ✅ Testes falharam por código incorreto
- ✅ Syntax errors ou bugs introduzidos
- ✅ Lógica de negócio incorreta

**Tratamento:**
```python
try:
    # Executar evolução
    result = attempt_evolution()
except NetworkError as e:
    # Erro externo - não punir
    log_external_error(e)
    retry_later()
except TestFailure as e:
    # Falha de lógica - aplicar punição
    evolution_service.log_deploy_result(success=False)
```

## Monitoramento e Métricas

### Métricas de Evolução

```python
metrics = auto_evolution.get_success_metrics()

print(f"Total de missões: {metrics['total_missions']}")
print(f"Completadas: {metrics['completed']}")
print(f"Em progresso: {metrics['in_progress']}")
print(f"Planejadas: {metrics['planned']}")
print(f"Progresso: {metrics['completion_percentage']}%")
```

### Dashboard de Status

O status de evolução pode ser visualizado:

1. **GitHub Actions**: Workflow runs em `.github/workflows/auto_evolution_trigger.yml`
2. **CLI**: `python scripts/show_rl_status.py`
3. **API**: Endpoint `/api/evolution/status` (se habilitado)

## Casos de Uso

### Caso 1: PR Normal Merged

```
1. Dev faz PR: "Fix typo in README"
2. PR é aprovado e merged na main
3. Auto-Evolution Trigger:
   - ✅ PR merged? Sim
   - ✅ É auto-evolução? Não
   - ✅ Tem missão no ROADMAP? Sim
   - 🚀 Inicia evolução automática
```

### Caso 2: PR de Auto-Evolução Merged

```
1. Jarvis cria PR: "[Auto-Evolution] Implement graceful pip failure"
2. Comandante aprova e faz merge
3. Auto-Evolution Trigger:
   - ✅ PR merged? Sim
   - ❌ É auto-evolução? Sim (keyword detectada)
   - ⏸️ Loop evitado, não executa
```

### Caso 3: Sem Missão Disponível

```
1. Dev faz PR: "Add feature X"
2. PR é aprovado e merged
3. Auto-Evolution Trigger:
   - ✅ PR merged? Sim
   - ✅ É auto-evolução? Não
   - ❌ Tem missão no ROADMAP? Não (todas completas)
   - ⏸️ Nenhuma ação tomada
```

## Troubleshooting

### Problema: Workflow não está sendo triggado

**Verificar:**
1. PR foi merged na main?
2. Workflow existe em `.github/workflows/auto_evolution_trigger.yml`?
3. Permissões do workflow estão corretas?

### Problema: Loop infinito de PRs

**Verificar:**
1. PRs de auto-evolução têm keywords no título?
2. Labels `auto-evolution` estão sendo aplicadas?
3. Método `is_auto_evolution_pr()` está funcionando?

### Problema: Nenhuma missão encontrada

**Verificar:**
1. ROADMAP.md existe em `docs/ROADMAP.md`?
2. Missões têm status correto (🔄, 📋)?
3. Há missões não completadas?

### Problema: Jarvis tenta repetidamente resolver missão já completa

**Solução:**
O sistema agora usa `find_next_mission_with_auto_complete()` que:
1. Detecta quando uma missão já está completa
2. Automaticamente marca a missão no ROADMAP.md como ✅
3. Move para a próxima missão no mesmo ciclo

Se o problema persistir:
1. Verifique se o workflow usa `find_next_mission_with_auto_complete()`
2. Verifique logs para ver se a marcação automática está funcionando
3. Manualmente marque a missão no ROADMAP.md como completa

## Auto-Completion de Missões

### O que é?

O sistema de auto-completion detecta quando uma missão marcada como 🔄 (em progresso) ou 📋 (planejada) já foi completada, e automaticamente:
1. Atualiza o ROADMAP.md marcando a missão como ✅
2. Busca a próxima missão disponível
3. Continua o ciclo de evolução sem intervenção humana

### Como funciona?

```python
# Workflow usa este método (com auto-complete)
next_mission = auto_evolution.find_next_mission_with_auto_complete()

# Internamente:
# 1. Busca próxima missão
# 2. Verifica se já está completa (heurísticas)
# 3. Se completa: marca no ROADMAP e busca próxima
# 4. Repete até encontrar missão não completa ou esgotar opções
```

### Vantagens

- **Evita loops cognitivos**: Jarvis não fica preso tentando resolver missões já completas
- **Auto-atualização do ROADMAP**: Mantém a documentação sincronizada
- **Eficiência**: Reduz ciclos de evolução desperdiçados
- **Transparência**: Logs mostram quando missões são auto-completadas

### Limitações Atuais

O método `is_mission_likely_completed()` é atualmente um placeholder que retorna `False`.
Implementações futuras podem incluir:
- Análise de código para detectar features implementadas
- Verificação de testes relacionados
- Análise de histórico do Git
- Validação de commits recentes

## Desenvolvimento Futuro

### Planejado
- [x] Auto-completion de missões já finalizadas
- [ ] Integração completa com GitHub Copilot Agent para implementação automática
- [ ] Análise de viabilidade antes de tentar evolução
- [ ] Heurísticas avançadas para detectar missões completas
- [ ] A/B testing de diferentes estratégias de evolução
- [ ] Dashboard web para visualização de evolução

### Em Consideração
- [ ] Auto-merge de PRs de baixo risco
- [ ] Notificações Slack/Discord quando evolução é iniciada
- [ ] Machine learning para prever sucesso de evolução
- [ ] Rollback automático se evolução quebra produção

## Sistema de Evolução Marvel

### O que é?

O **Sistema de Evolução Marvel** é uma extensão do sistema de auto-evolução que foca especificamente nas **9 habilidades de nível Marvel** (CHAPTER_9 do JARVIS_OBJECTIVES_MAP).

Enquanto o sistema base de auto-evolução gerencia missões gerais do ROADMAP.md, o sistema Marvel gerencia a evolução para capacidades avançadas comparáveis ao J.A.R.V.I.S. da Marvel.

### Componentes Marvel

1. **MARVEL_ROADMAP.md** - Apostila de Evolução com as 9 habilidades Marvel
2. **MarvelEvolutionService** - Serviço especializado para evolução Marvel
3. **demo_marvel_evolution.py** - Script de demonstração do ciclo Marvel

### As 9 Habilidades Marvel

1. **Interface Holográfica** - Antecipar necessidades do usuário (Cap. 94)
2. **Diagnóstico de Armadura** - Propor soluções proativamente (Cap. 95)
3. **Controle de Periféricos** - Ação proativa e segura (Cap. 96)
4. **Sistemas Integrados** - Coordenar físico e digital (Cap. 97)
5. **Copiloto Cognitivo** - Operar como assistente mental (Cap. 98)
6. **Alinhamento Contínuo** - Manter sintonia com usuário (Cap. 99)
7. **Evolução Preservando Identidade** - Evoluir sem perder essência (Cap. 100)
8. **Sustentabilidade Econômica** - Autossuficiência financeira (Cap. 101)
9. **Infraestrutura Cognitiva Pessoal** - Fundação do pensamento (Cap. 102)

### Ciclo de Aprendizado Marvel

```python
from app.application.services.marvel_evolution import MarvelEvolutionService

# 1. Inicializar serviço
marvel_service = MarvelEvolutionService()

# 2. Encontrar próxima habilidade Marvel
next_skill = marvel_service.find_next_marvel_skill()

# 3. Implementar scripts necessários
# (baseado em next_skill['scripts_needed'])

# 4. Executar Metabolismo (pytest)
test_results = {'passed': 4, 'total': 4, 'success_rate': 100.0}

# 5. Validar habilidade
is_valid = marvel_service.is_skill_validated_by_metabolismo(
    skill_number=next_skill['skill']['number'],
    test_results=test_results
)

# 6. Se aprovado, marcar como aprendida
if is_valid:
    marvel_service.mark_marvel_skill_as_learned(next_skill['skill']['number'])
    
    # 7. Gerar relatório para o Comandante
    report = marvel_service.generate_progress_report(
        skill_name=next_skill['skill']['name'],
        tests_passed=4,
        tests_total=4,
        learning_time="2 horas"
    )
    print(report)
```

### Relatório de Progresso Marvel

Exemplo de saída após aprender uma habilidade:

```
🤖 Comandante, mais uma habilidade do Jarvis Marvel foi integrada ao meu DNA.

Habilidade Aprendida: Interface Holográfica - Antecipar Necessidades do Usuário
Testes Passaram: 4/4 (100%)
Tempo de Aprendizado: 2 horas

📈 Progresso Geral: 1/9 habilidades Marvel (11.1% completo)
Estamos 11.1% mais próximos do Xerife Marvel.

Próxima Missão: Diagnóstico de Armadura - Propor Soluções Proativamente
```

### Diferenças: Auto-Evolução vs Marvel

| Aspecto | Auto-Evolução | Marvel Evolution |
|---------|---------------|------------------|
| Roadmap | `docs/ROADMAP.md` | `docs/MARVEL_ROADMAP.md` |
| Foco | Missões gerais | 9 habilidades Marvel |
| Serviço | `AutoEvolutionService` | `MarvelEvolutionService` |
| Capacidades | Todas (IDs 1-102) | Apenas CHAPTER_9 (IDs 94-102) |
| Relatórios | Genérico | Português, tema Marvel |
| Objetivo | Estabilização geral | Nível Marvel (J.A.R.V.I.S.) |

### Demonstração

Execute o script de demonstração para ver o sistema Marvel em ação:

```bash
python scripts/demo_marvel_evolution.py
```

### Referências Marvel

- [MARVEL_ROADMAP.md](./MARVEL_ROADMAP.md) - Apostila de Evolução Marvel
- [marvel_evolution.py](../app/application/services/marvel_evolution.py) - Serviço Marvel
- [demo_marvel_evolution.py](../scripts/demo_marvel_evolution.py) - Demo do sistema
- [test_marvel_evolution.py](../tests/test_marvel_evolution.py) - Testes do sistema

---

## Referências

- [ROADMAP.md](../ROADMAP.md) - Roadmap do projeto
- [MARVEL_ROADMAP.md](./MARVEL_ROADMAP.md) - **NOVO:** Apostila de Evolução Marvel
- [RL_EVOLUTION_MODULE.md](./RL_EVOLUTION_MODULE.md) - Sistema de Reinforcement Learning
- [evolution_loop.py](../app/application/services/evolution_loop.py) - Serviço de RL
- [auto_evolution.py](../app/application/services/auto_evolution.py) - Serviço de auto-evolução
- [marvel_evolution.py](../app/application/services/marvel_evolution.py) - **NOVO:** Serviço de evolução Marvel

---

**Última Atualização**: 2026-02-13  
**Mantido por**: Equipe Jarvis  
**Status**: ✅ Implementado e Testado (Auto-Evolução + Marvel)
