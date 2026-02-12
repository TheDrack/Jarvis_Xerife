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

**Principais métodos:**

```python
from app.application.services.auto_evolution import AutoEvolutionService

# Inicializar serviço
auto_evolution = AutoEvolutionService()

# Encontrar próxima missão
mission = auto_evolution.find_next_mission()
# Retorna: {
#   'mission': {...},
#   'section': 'AGORA',
#   'priority': 'high'
# }

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

## Desenvolvimento Futuro

### Planejado
- [ ] Integração completa com GitHub Copilot Agent para implementação automática
- [ ] Análise de viabilidade antes de tentar evolução
- [ ] A/B testing de diferentes estratégias de evolução
- [ ] Dashboard web para visualização de evolução

### Em Consideração
- [ ] Auto-merge de PRs de baixo risco
- [ ] Notificações Slack/Discord quando evolução é iniciada
- [ ] Machine learning para prever sucesso de evolução
- [ ] Rollback automático se evolução quebra produção

## Referências

- [ROADMAP.md](../ROADMAP.md) - Roadmap do projeto
- [RL_EVOLUTION_MODULE.md](./RL_EVOLUTION_MODULE.md) - Sistema de Reinforcement Learning
- [evolution_loop.py](../app/application/services/evolution_loop.py) - Serviço de RL
- [auto_evolution.py](../app/application/services/auto_evolution.py) - Serviço de auto-evolução

---

**Última Atualização**: 2026-02-12  
**Mantido por**: Equipe Jarvis  
**Status**: ✅ Implementado e Testado
